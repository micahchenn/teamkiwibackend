"""
Square REST API (Payments v2) — server-side only. Uses access token from env.
https://developer.squareup.com/reference/square/payments-api/create-payment
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx
from django.conf import settings


class SquareAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


def _square_base_url() -> str:
    if getattr(settings, "SQUARE_ENVIRONMENT", "sandbox") == "production":
        return "https://connect.squareup.com"
    return "https://connect.squareupsandbox.com"


def _square_version() -> str:
    return getattr(settings, "SQUARE_API_VERSION", "2024-11-20")


class SquarePaymentService:
    def __init__(self, access_token: str):
        if not access_token or not access_token.strip():
            raise ValueError("SQUARE_ACCESS_TOKEN is required")
        self._token = access_token.strip()
        self._base = _square_base_url()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Square-Version": _square_version(),
        }

    def create_payment(
        self,
        *,
        source_id: str,
        amount_cents: int,
        currency: str,
        location_id: str,
        idempotency_key: str | None = None,
        reference_id: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        if not location_id:
            raise ValueError("location_id is required")

        body: dict[str, Any] = {
            "source_id": source_id,
            "idempotency_key": idempotency_key or str(uuid.uuid4()),
            "amount_money": {
                "amount": int(amount_cents),
                "currency": (currency or "USD").upper(),
            },
            "location_id": location_id,
        }
        if reference_id:
            body["reference_id"] = reference_id[:40]
        if note:
            body["note"] = note[:500]

        url = f"{self._base}/v2/payments"
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.post(url, headers=self._headers(), json=body)
        except httpx.RequestError as e:
            raise SquareAPIError(f"Square request failed: {e}") from e

        try:
            data = r.json()
        except ValueError:
            data = {"raw": r.text}

        if r.status_code >= 400:
            msg = self._format_error(data) or f"Square HTTP {r.status_code}"
            raise SquareAPIError(msg, status_code=r.status_code, body=data)

        return data if isinstance(data, dict) else {"result": data}

    @staticmethod
    def _format_error(data: Any) -> str | None:
        if not isinstance(data, dict):
            return None
        errs = data.get("errors")
        if isinstance(errs, list) and errs:
            e0 = errs[0]
            if isinstance(e0, dict):
                return e0.get("detail") or e0.get("code") or str(e0)
        return data.get("message")


def get_square_payment_service() -> SquarePaymentService:
    return SquarePaymentService(settings.SQUARE_ACCESS_TOKEN)
