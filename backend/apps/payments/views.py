from __future__ import annotations

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.locks.provisioning import ensure_access_code_for_square_payment
from apps.payments.repository import get_booking_repository
from apps.payments.serializers import SquarePaymentRequestSerializer
from services.email_service import send_booking_confirmation_email
from services.square_service import SquareAPIError, SquarePaymentService, get_square_payment_service


def _validation_error_response(errors) -> Response:
    if errors.get("non_field_errors"):
        return Response({"error": str(errors["non_field_errors"][0])}, status=status.HTTP_400_BAD_REQUEST)
    if isinstance(errors, dict):
        for _k, v in errors.items():
            if isinstance(v, list) and v:
                return Response({"error": str(v[0])}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"error": str(v)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"error": "Invalid request."}, status=status.HTTP_400_BAD_REQUEST)


class SquareConfigView(APIView):
    """GET /api/square/config — Web Payments SDK (applicationId + locationId)."""

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, *args, **kwargs):
        app_id = getattr(settings, "SQUARE_APPLICATION_ID", "") or ""
        app_id = str(app_id).strip()
        loc = str(getattr(settings, "SQUARE_LOCATION_ID", "") or "").strip()
        if not app_id or not loc:
            return Response(
                {
                    "error": "Square is not configured (set SQUARE_APPLICATION_ID or REACT_APP_SQUARE_APPLICATION_ID and SQUARE_LOCATION_ID).",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"applicationId": app_id, "locationId": loc})


class SquarePaymentView(APIView):
    """POST /api/square/payments — charge with Square token; persist booking in MongoDB."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request, *args, **kwargs):
        ser = SquarePaymentRequestSerializer(data=request.data)
        if not ser.is_valid():
            return _validation_error_response(ser.errors)

        d = ser.validated_data
        source_id = d["sourceId"]
        amount_cents = d["amountCents"]
        currency = d.get("currency") or "USD"
        note = (d.get("note") or "").strip() or None
        reference_id = str(d["referenceId"])
        booking = d.get("booking")
        booking_dict = dict(booking) if booking is not None else None

        loc = (getattr(settings, "SQUARE_LOCATION_ID", None) or "").strip()
        if not loc:
            return Response(
                {"error": "SQUARE_LOCATION_ID is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            sq = get_square_payment_service()
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        try:
            result = sq.create_payment(
                source_id=source_id,
                amount_cents=amount_cents,
                currency=currency,
                location_id=loc,
                idempotency_key=reference_id[:45],
                reference_id=reference_id,
                note=note,
            )
        except SquareAPIError as e:
            repo = get_booking_repository()
            repo.upsert_payment_result(
                reference_id=reference_id,
                customer_name=(d.get("customerName") or "").strip() or None,
                customer_email=(d.get("customerEmail") or "").strip() or None,
                customer_phone=(d.get("customerPhone") or "").strip() or None,
                booking=booking_dict,
                amount_cents=amount_cents,
                currency=currency,
                note=note,
                square_payment_id=None,
                square_status=None,
                receipt_url=None,
                payment_status="failed",
            )
            msg = str(e)
            if getattr(e, "body", None) and isinstance(e.body, dict):
                msg = SquarePaymentService._format_error(e.body) or msg
            return Response({"error": msg or "Square payment failed."}, status=status.HTTP_502_BAD_GATEWAY)

        payment = result.get("payment") or {}
        pay_id = payment.get("id")
        pay_status = (payment.get("status") or "UNKNOWN").upper()
        receipt_url = payment.get("receipt_url") or payment.get("receiptUrl")

        repo = get_booking_repository()
        customer_email = (d.get("customerEmail") or "").strip() or None
        payment_status = "paid" if pay_status in ("COMPLETED", "APPROVED") else pay_status.lower()
        saved = repo.upsert_payment_result(
            reference_id=reference_id,
            customer_name=(d.get("customerName") or "").strip() or None,
            customer_email=customer_email,
            customer_phone=(d.get("customerPhone") or "").strip() or None,
            booking=booking_dict,
            amount_cents=amount_cents,
            currency=currency,
            note=note,
            square_payment_id=pay_id,
            square_status=pay_status,
            receipt_url=receipt_url,
            payment_status=payment_status,
        )

        provision = None
        if payment_status == "paid":
            provision = ensure_access_code_for_square_payment(
                reference_id,
                booking_dict,
                customer_name=(d.get("customerName") or "").strip() or None,
                customer_email=customer_email,
            )
        access_codes = provision.access_codes if provision else []
        seam_sync_failed = provision.seam_sync_failed if provision else False

        if (
            customer_email
            and payment_status == "paid"
            and not seam_sync_failed
        ):
            send_booking_confirmation_email(
                customer_email,
                customer_name=(d.get("customerName") or "").strip() or None,
                reference_id=reference_id,
                amount_cents=amount_cents,
                currency=currency,
                receipt_url=receipt_url,
                payment_status=payment_status,
                access_code_docs=access_codes,
            )

        lock_ok = bool(access_codes) and not seam_sync_failed
        lock_message = None
        if payment_status == "paid" and booking_dict and (booking_dict.get("visitStart") or booking_dict.get("visitEnd")):
            if seam_sync_failed:
                lock_message = (
                    "Payment succeeded, but the door code could not be programmed on the lock. "
                    "Contact support with your reference number; do not assume access until confirmed."
                )
            elif not access_codes:
                lock_message = (
                    "Payment recorded. No access code was issued (stay may have ended or dates were missing)."
                )

        return Response(
            {
                "success": True,
                "paymentId": pay_id,
                "status": pay_status,
                "receiptUrl": receipt_url,
                "referenceId": reference_id,
                "booking": saved.get("booking") or booking_dict or {},
                "accessCodes": access_codes,
                "seamSyncFailed": seam_sync_failed,
                "lockProvision": {
                    "ok": lock_ok,
                    "codesIssued": len(access_codes),
                    "seamSyncFailed": seam_sync_failed,
                    "message": lock_message,
                },
            },
            status=status.HTTP_200_OK,
        )
