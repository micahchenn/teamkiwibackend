"""
Create or reuse lock access codes after a successful booking payment.

``visitStart`` / ``visitEnd`` are interpreted as calendar dates in ``BOOKING_TIMEZONE``
(default America/Chicago). The code is valid **immediately** when payment completes
(Seam/Mongo start = now UTC) through **end of the visitEnd calendar day** in that zone.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

from django.conf import settings

from apps.locks.access_code_name import seam_access_code_name
from apps.locks.booking_timezone import parse_visit_dates, utc_now, visit_end_to_expires_utc
from apps.locks.repository import get_access_code_repository
from apps.locks.seam import get_seam_service
from services.seam_service import SeamAPIError

logger = logging.getLogger(__name__)


class SquarePaymentAccessResult(NamedTuple):
    """``seam_sync_failed`` means Seam was required but did not succeed — skip confirmation email."""

    access_codes: list[dict[str, Any]]
    seam_sync_failed: bool


def _device_id() -> str | None:
    raw = getattr(settings, "SEAM_DEVICE_ID", None)
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


def ensure_access_code_for_square_payment(
    reference_id: str,
    booking: dict[str, Any] | None,
    *,
    customer_name: str | None,
    customer_email: str | None,
) -> SquarePaymentAccessResult:
    """
    Return existing codes for this booking_id, or create one from visit dates
    and sync to Seam when SEAM_DEVICE_ID is set.

    Lock becomes active **immediately** at payment time; it expires at the end of
    ``visitEnd`` in the property timezone (not UTC midnight).

    If the device is configured and Seam sync does not succeed, the Mongo document is
    removed and ``seam_sync_failed`` is True (caller should not send confirmation email).
    """
    repo = get_access_code_repository()
    ref = (reference_id or "").strip()
    if not ref:
        return SquarePaymentAccessResult([], False)

    existing = repo.list_by_booking_id(ref)
    if existing:
        return SquarePaymentAccessResult(existing, False)

    dates = parse_visit_dates(booking)
    if not dates:
        logger.info(
            "No visitStart/visitEnd on booking; skipping auto access code for reference %s",
            ref,
        )
        return SquarePaymentAccessResult([], False)

    _visit_start_date, visit_end_date = dates
    expires_at = visit_end_to_expires_utc(visit_end_date)
    starts_at = utc_now()

    if expires_at <= starts_at:
        logger.info(
            "Stay already ended in booking window for reference %s (visitEnd=%s)",
            ref,
            visit_end_date,
        )
        return SquarePaymentAccessResult([], False)

    device_id = _device_id()
    lock_name = None
    if booking:
        lock_name = (booking.get("product") or "").strip() or None

    try:
        doc = repo.create(
            expires_at=expires_at,
            starts_at=starts_at,
            device_id=device_id,
            lock_name=lock_name or "Stay",
            lock_location=None,
            booking_id=ref,
            customer_name=customer_name,
            customer_email=customer_email,
            notes=None,
            seam_access_code_id=None,
        )
    except (ValueError, RuntimeError) as e:
        logger.exception("Could not create access code for booking %s: %s", ref, e)
        return SquarePaymentAccessResult([], False)

    if not device_id:
        return SquarePaymentAccessResult([doc], False)

    base = doc.get("lock_name") or "Access"
    name = seam_access_code_name(
        doc["code"],
        lock_name_base=base,
        booking_reference=ref,
    )
    try:
        seam = get_seam_service()
    except ValueError as e:
        logger.warning("Seam not configured for booking %s: %s", ref, e)
        repo.delete_by_id(doc["id"])
        return SquarePaymentAccessResult([], True)

    try:
        resp = seam.create_access_code(
            device_id=device_id,
            code=doc["code"],
            name=name,
            starts_at=starts_at,
            ends_at=expires_at,
        )
        ac = resp.get("access_code") or {}
        aid = ac.get("access_code_id")
        patch_ok: dict[str, Any] = {
            "seam_access_code_id": aid,
            "seam_sync_status": "ok",
            "seam_sync_error": None,
            "seam_error_body": None,
            "starts_at": starts_at,
            "expires_at": expires_at,
        }
        repo.patch_by_id(doc["id"], patch_ok)
    except SeamAPIError as e:
        err = str(e)[:2000]
        body = getattr(e, "body", None)
        repo.delete_by_id(doc["id"])
        logger.warning(
            "Seam access_codes/create failed for booking %s: %s body=%s",
            ref,
            err,
            body,
        )
        return SquarePaymentAccessResult([], True)

    return SquarePaymentAccessResult([repo.get_by_id(doc["id"]) or doc], False)
