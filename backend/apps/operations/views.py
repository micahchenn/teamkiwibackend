from __future__ import annotations

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.operations.summary import build_summary

logger = logging.getLogger(__name__)


def _operations_key_valid(request) -> bool:
    expected = (getattr(settings, "OPERATIONS_API_KEY", None) or "").strip()
    if not expected:
        return False
    supplied = (request.headers.get("X-Operations-Key") or "").strip()
    return supplied == expected


class OperationsSummaryView(APIView):
    """
    GET /api/operations/summary/

    Staff / analytics snapshot (bookings + lock codes). Protected by env
    OPERATIONS_API_KEY — send header ``X-Operations-Key: <same value>``.

    For a non-technical client, expose this through a small password-protected
    admin UI or a no-code tool (e.g. Retool) that stores the key server-side,
    not in a public JavaScript bundle.
    """

    authentication_classes: list = []
    permission_classes: list = []

    def get(self, request, *args, **kwargs):
        if not (getattr(settings, "OPERATIONS_API_KEY", None) or "").strip():
            return Response(
                {
                    "error": "Operations console is not configured. Set OPERATIONS_API_KEY in the environment.",
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if not _operations_key_valid(request):
            return Response({"error": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            data = build_summary()
        except Exception:
            logger.exception("operations summary failed")
            return Response(
                {"error": "Could not load summary."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(data)
