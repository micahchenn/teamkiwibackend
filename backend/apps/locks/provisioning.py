"""
Create or reuse lock access codes after a successful booking payment.

``visitStart`` / ``visitEnd`` are interpreted as calendar dates in ``BOOKING_TIMEZONE``
(default America/Chicago). The code is valid **immediately** when payment completes
(Seam/Mongo start = now UTC) through **end of the visitEnd calendar day** in that zone.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any, NamedTuple

from django.conf import settings

from apps.locks.access_code_name import seam_access_code_name
from apps.locks.booking_safety import validate_booking_for_access_code
from apps.locks.booking_timezone import parse_visit_dates, utc_now, visit_end_to_expires_utc
from apps.locks.repository import get_access_code_repository
from apps.locks.seam import get_seam_service
from apps.locks.seam_resolve import resolve_seam_device_id_for_payment
from services.email_service import send_admin_access_code_failure_email
from services.seam_service import SeamAPIError, SeamService

logger = logging.getLogger(__name__)


def _retryable_duplicate_pin(exc: SeamAPIError) -> bool:
    """Kwikset duplicate PIN / conflict — new random code may succeed."""
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        for er in body.get("errors") or []:
            if isinstance(er, dict) and er.get("error_code") == "kwikset_unable_to_confirm_code":
                return True
    msg = str(exc).lower()
    if "kwikset_unable_to_confirm" in msg:
        return True
    return False


def _normalize_backup_pin(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = "".join(c for c in str(raw) if c.isdigit())
    if len(digits) != 6:
        logger.warning("SEAM_BACKUP_STATIC_CODE must be exactly 6 digits; backup email disabled.")
        return None
    return digits


def _resolve_backup_access_for_email(
    *,
    seam: SeamService | None,
    visit_end_date,
    reference_id: str,
) -> dict[str, Any] | None:
    """
    Synthetic row for email only — not persisted to Mongo.

    Configured ``SEAM_BACKUP_CODE_*_ID`` values are **shuffled** each time; the first
    ``access_codes/get`` that returns a valid 6-digit code with no errors wins, so guests
    spread across backups instead of always getting the same one. Falls back to
    ``SEAM_BACKUP_STATIC_CODE`` if Seam is unavailable or every fetch fails.
    """
    starts_at = utc_now()
    expires_at = visit_end_to_expires_utc(visit_end_date)
    base: dict[str, Any] = {
        "starts_at": starts_at,
        "expires_at": expires_at,
        "booking_id": reference_id,
        "status": "backup_static",
        "seam_sync_status": "backup_static",
        "lock_location": "Backup entry",
    }

    ids: list[str] = list(getattr(settings, "SEAM_BACKUP_CODE_IDS", None) or [])
    if seam and ids:
        shuffled = list(ids)
        secrets.SystemRandom().shuffle(shuffled)
        for aid in shuffled:
            try:
                ac = seam.get_access_code(aid)
            except SeamAPIError as e:
                logger.warning(
                    "Seam backup access_codes/get failed for access_code_id=%s: %s",
                    aid,
                    e,
                )
                continue
            errs = ac.get("errors")
            if isinstance(errs, list) and len(errs) > 0:
                logger.warning(
                    "Seam backup access code %s has errors; trying next: %s",
                    aid,
                    errs,
                )
                continue
            pin = _normalize_backup_pin(str(ac.get("code") or ""))
            if not pin:
                continue
            label = (ac.get("name") or "").strip() or getattr(
                settings, "SEAM_BACKUP_LOCK_NAME", "KIWIBACKUPKEY"
            )
            label = str(label).strip() or "KIWIBACKUPKEY"
            return {
                **base,
                "id": f"backup-seam-{aid[:8]}",
                "code": pin,
                "lock_name": label,
                "seam_backup_access_code_id": aid,
            }

    pin = _normalize_backup_pin(getattr(settings, "SEAM_BACKUP_STATIC_CODE", None))
    if not pin:
        return None
    label = getattr(settings, "SEAM_BACKUP_LOCK_NAME", None) or "KIWIBACKUPKEY"
    label = str(label).strip() or "KIWIBACKUPKEY"
    return {
        **base,
        "id": "backup-static",
        "code": pin,
        "lock_name": label,
    }


class SquarePaymentAccessResult(NamedTuple):
    """
    ``seam_sync_failed`` — primary timed PIN could not be programmed and no backup was available;
    skip confirmation email with access codes.

    ``used_backup_access`` — guest email used a permanent Seam backup (``SEAM_BACKUP_CODE_*_ID``)
    or ``SEAM_BACKUP_STATIC_CODE`` after primary Seam failed.
    """

    access_codes: list[dict[str, Any]]
    seam_sync_failed: bool
    used_backup_access: bool = False


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

    If the primary device is configured and Seam fails (including Kwikset duplicate-PIN
    errors), the Mongo row is removed and up to ``SEAM_PIN_MAX_ATTEMPTS`` new random codes
    are tried. If all attempts fail, one of ``SEAM_BACKUP_CODE_1_ID`` … ``_5_ID`` is chosen at
    random (shuffle, then first successful ``access_codes/get``); if none work,
    ``SEAM_BACKUP_STATIC_CODE`` is used when set.
    Otherwise ``seam_sync_failed`` is True and no access code is emailed.
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

    ok, reason = validate_booking_for_access_code(booking, parsed_dates=dates)
    if not ok:
        logger.warning(
            "Access code blocked for reference %s: %s",
            ref,
            reason,
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

    device_id = resolve_seam_device_id_for_payment()
    lock_name = None
    if booking:
        lock_name = (booking.get("product") or "").strip() or None

    max_pin_attempts = int(getattr(settings, "SEAM_PIN_MAX_ATTEMPTS", 5))

    for attempt in range(1, max_pin_attempts + 1):
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
            customer_name=customer_name,
        )
        try:
            seam = get_seam_service()
        except ValueError as e:
            logger.warning("Seam not configured for booking %s: %s", ref, e)
            repo.delete_by_id(doc["id"])
            backup = _resolve_backup_access_for_email(
                seam=None,
                visit_end_date=visit_end_date,
                reference_id=ref,
            )
            send_admin_access_code_failure_email(
                reference_id=ref,
                customer_name=customer_name,
                customer_email=customer_email,
                error_message=f"Seam API not configured: {e}",
                guest_received_backup_pin=bool(backup),
            )
            if backup:
                logger.warning("Using backup static PIN for reference %s (Seam not configured).", ref)
                return SquarePaymentAccessResult([backup], False, True)
            return SquarePaymentAccessResult([], True)

        last_aid: str | None = None
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
            if not aid:
                raise SeamAPIError(
                    "Seam access_codes/create did not return access_code_id",
                    body=resp,
                )
            last_aid = aid
            if not getattr(settings, "SEAM_SKIP_ACCESS_CODE_SET_POLL", False):
                seam.wait_until_access_code_set_on_device(
                    aid,
                    timeout_seconds=float(
                        getattr(settings, "SEAM_ACCESS_CODE_SET_TIMEOUT_SECONDS", 120.0)
                    ),
                    poll_interval_seconds=float(
                        getattr(settings, "SEAM_ACCESS_CODE_POLL_INTERVAL_SECONDS", 2.0)
                    ),
                )
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
            if last_aid and device_id:
                try:
                    seam.delete_access_code(device_id, last_aid)
                except SeamAPIError as del_exc:
                    logger.warning(
                        "Seam access_codes/delete failed for %s (booking %s): %s",
                        last_aid,
                        ref,
                        del_exc,
                    )
            if _retryable_duplicate_pin(e) and attempt < max_pin_attempts:
                logger.warning(
                    "Seam PIN conflict for booking %s (attempt %s/%s), retrying with new code: %s",
                    ref,
                    attempt,
                    max_pin_attempts,
                    err,
                )
                continue
            logger.warning(
                "Seam access_codes/create failed for booking %s: %s body=%s",
                ref,
                err,
                body,
            )
            backup = _resolve_backup_access_for_email(
                seam=seam,
                visit_end_date=visit_end_date,
                reference_id=ref,
            )
            send_admin_access_code_failure_email(
                reference_id=ref,
                customer_name=customer_name,
                customer_email=customer_email,
                error_message=err,
                error_body=body,
                guest_received_backup_pin=bool(backup),
            )
            if backup:
                logger.warning(
                    "Using backup PIN for reference %s (lock label %r).",
                    ref,
                    backup.get("lock_name"),
                )
                return SquarePaymentAccessResult([backup], False, True)
            return SquarePaymentAccessResult([], True)

        return SquarePaymentAccessResult([repo.get_by_id(doc["id"]) or doc], False)
