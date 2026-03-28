from __future__ import annotations

from django.conf import settings
from django.utils import timezone as dj_tz
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.locks.repository import get_access_code_repository
from apps.locks.serializers import LockCodeCreateSerializer, LockCodeReadSerializer
from apps.locks.seam import get_seam_service
from services.seam_service import SeamAPIError


class LockCodeCreateView(APIView):
    """POST /api/lock-codes/ — random 6-digit code in MongoDB; optional Seam PIN program."""

    def post(self, request, *args, **kwargs):
        ser = LockCodeCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        device_id = ser.clean_optional_str("device_id", data) or getattr(
            settings, "SEAM_DEVICE_ID", None
        )

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
        out = {**doc, "seam_sync": "skipped"}

        if device_id and not prelinked_seam:
            name = doc.get("lock_name") or f"Access {doc['code']}"
            try:
                seam = get_seam_service()
            except ValueError as e:
                repo.patch_by_id(
                    doc["id"],
                    {"seam_sync_status": "failed", "seam_sync_error": str(e)},
                )
                out.update(seam_sync="failed", seam_sync_error=str(e))
                return Response(out, status=status.HTTP_201_CREATED)

            try:
                resp = seam.create_access_code(
                    device_id=device_id,
                    code=doc["code"],
                    name=name,
                    starts_at=starts,
                    ends_at=expires,
                )
                ac = resp.get("access_code") or {}
                aid = ac.get("access_code_id")
                repo.patch_by_id(
                    doc["id"],
                    {
                        "seam_access_code_id": aid,
                        "seam_sync_status": "ok",
                        "seam_sync_error": None,
                    },
                )
                out.update(
                    seam_sync="ok",
                    seam_access_code_id=aid,
                    seam_sync_status="ok",
                )
            except SeamAPIError as e:
                err = str(e)[:2000]
                repo.patch_by_id(
                    doc["id"],
                    {"seam_sync_status": "failed", "seam_sync_error": err},
                )
                body = getattr(e, "body", None)
                out.update(
                    seam_sync="failed",
                    seam_sync_status="failed",
                    seam_sync_error=err,
                    seam_error_body=body,
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
