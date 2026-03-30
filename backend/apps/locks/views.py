from __future__ import annotations

from django.conf import settings
from django.utils import timezone as dj_tz
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.locks.access_code_name import seam_access_code_name
from apps.locks.repository import get_access_code_repository
from apps.locks.serializers import LockCodeCreateSerializer, LockCodeReadSerializer
from apps.locks.seam import get_seam_service
from apps.locks.seam_resolve import resolve_seam_device_id_for_payment
from apps.locks.seam_window import clamp_seam_window
from services.seam_service import SeamAPIError, parse_seam_iso_datetime


class LockCodeCreateView(APIView):
    """POST /api/lock-codes/ — random 6-digit code in MongoDB; optional Seam PIN program."""

    def post(self, request, *args, **kwargs):
        ser = LockCodeCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        device_id = ser.clean_optional_str("device_id", data) or resolve_seam_device_id_for_payment()

        repo = get_access_code_repository()
        try:
            doc = repo.create(
                expires_at=data["expires_at"],
                starts_at=data.get("starts_at"),
                device_id=device_id,
                lock_name=ser.clean_optional_str("lock_name", data),
                lock_location=ser.clean_optional_str("lock_location", data),
                booking_id=ser.clean_optional_str("booking_id", data),
                customer_name=ser.clean_optional_str("customer_name", data),
                customer_email=ser.clean_optional_str("customer_email", data),
                notes=ser.clean_optional_str("notes", data),
                seam_access_code_id=ser.clean_optional_str("seam_access_code_id", data),
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except RuntimeError as e:
            return Response({"detail": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        starts = data.get("starts_at") or dj_tz.now()
        expires = data["expires_at"]
        device_id = doc.get("device_id")
        prelinked_seam = ser.clean_optional_str("seam_access_code_id", data)
        booking_ref = ser.clean_optional_str("booking_id", data) or doc.get("booking_id")
        out = {**doc, "seam_sync": "skipped"}

        if device_id and not prelinked_seam:
            base = doc.get("lock_name") or "Access"
            cust = ser.clean_optional_str("customer_name", data) or doc.get("customer_name")
            name = seam_access_code_name(
                doc["code"],
                lock_name_base=base,
                booking_reference=booking_ref,
                customer_name=cust,
            )
            try:
                seam = get_seam_service()
            except ValueError as e:
                repo.delete_by_id(doc["id"])
                return Response(
                    {"detail": str(e), "seam_sync": "failed"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            seam_window = clamp_seam_window(starts, expires)
            if seam_window is None:
                msg = "Access window already ended; cannot program lock."
                repo.delete_by_id(doc["id"])
                return Response(
                    {"detail": msg, "seam_sync": "failed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            seam_start, seam_end = seam_window
            try:
                resp = seam.create_access_code(
                    device_id=device_id,
                    code=doc["code"],
                    name=name,
                    starts_at=seam_start,
                    ends_at=seam_end,
                    prefer_native_scheduling=bool(
                        getattr(settings, "SEAM_PREFER_NATIVE_SCHEDULING", False)
                    ),
                )
                ac = resp.get("access_code") or {}
                aid = ac.get("access_code_id")
                if not aid:
                    raise SeamAPIError(
                        "Seam access_codes/create did not return access_code_id",
                        body=resp,
                    )
                if not getattr(settings, "SEAM_SKIP_ACCESS_CODE_SET_POLL", False):
                    final_ac = seam.wait_until_access_code_set_on_device(
                        aid,
                        timeout_seconds=float(
                            getattr(settings, "SEAM_ACCESS_CODE_SET_TIMEOUT_SECONDS", 120.0)
                        ),
                        poll_interval_seconds=float(
                            getattr(settings, "SEAM_ACCESS_CODE_POLL_INTERVAL_SECONDS", 2.0)
                        ),
                    )
                else:
                    final_ac = seam.get_access_code(aid)
                seam_start_eff = parse_seam_iso_datetime(final_ac.get("starts_at")) or seam_start
                seam_end_eff = parse_seam_iso_datetime(final_ac.get("ends_at")) or seam_end
                repo.patch_by_id(
                    doc["id"],
                    {
                        "seam_access_code_id": aid,
                        "seam_sync_status": "ok",
                        "seam_sync_error": None,
                        "seam_error_body": None,
                        "starts_at": seam_start_eff,
                        "expires_at": seam_end_eff,
                    },
                )
                out.update(
                    seam_sync="ok",
                    seam_access_code_id=aid,
                    seam_sync_status="ok",
                    starts_at=seam_start_eff,
                    expires_at=seam_end_eff,
                )
            except SeamAPIError as e:
                err = str(e)[:2000]
                body = getattr(e, "body", None)
                repo.delete_by_id(doc["id"])
                return Response(
                    {
                        "detail": "Seam could not program the lock; access code was not saved.",
                        "seam_sync": "failed",
                        "seam_sync_error": err,
                        "seam_error_body": body,
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )

        return Response(out, status=status.HTTP_201_CREATED)


class LockCodeDetailView(APIView):
    """GET /api/lock-codes/<id>/ — fetch by MongoDB ObjectId string."""

    def get(self, request, pk: str, *args, **kwargs):
        repo = get_access_code_repository()
        doc = repo.get_by_id(pk)
        if not doc:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(doc)


class LockCodeLookupView(APIView):
    """GET /api/lock-codes/lookup/?code=123456"""

    def get(self, request, *args, **kwargs):
        ser = LockCodeReadSerializer(data={"code": request.query_params.get("code", "")})
        ser.is_valid(raise_exception=True)
        repo = get_access_code_repository()
        doc = repo.get_by_code(ser.validated_data["code"])
        if not doc:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(doc)
