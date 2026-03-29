"""Transactional email: SendGrid Dynamic Templates (v3 API) or SMTP fallback."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone as dt_timezone
from typing import Any

import httpx
from django.conf import settings
from django.core.mail import send_mail

from apps.locks.booking_timezone import format_dt_central

logger = logging.getLogger(__name__)

SENDGRID_MAIL_SEND_URL = "https://api.sendgrid.com/v3/mail/send"


def _sendgrid_api_key() -> str:
    return (getattr(settings, "SENDGRID_API_KEY", None) or "").strip()


def _template_extra_from_env() -> dict[str, Any]:
    raw = (getattr(settings, "SENDGRID_TEMPLATE_EXTRA_JSON", None) or "").strip()
    if not raw:
        return {}
    try:
        out = json.loads(raw)
        return out if isinstance(out, dict) else {}
    except json.JSONDecodeError:
        logger.warning("SENDGRID_TEMPLATE_EXTRA_JSON is not valid JSON; ignoring.")
        return {}


def _smtp_configured() -> bool:
    return bool(getattr(settings, "EMAIL_HOST_PASSWORD", None))


def _admin_notification_recipients() -> list[str]:
    raw = getattr(settings, "ADMIN_EMAIL_NOTIFICATIONS", None) or ""
    return [x.strip() for x in str(raw).split(",") if x.strip()]


def send_admin_access_code_failure_email(
    *,
    reference_id: str,
    customer_name: str | None,
    customer_email: str | None,
    error_message: str,
    error_body: Any = None,
    guest_received_backup_pin: bool = False,
) -> None:
    """
    Notify operators when primary Seam PIN provisioning fails (create, poll, or missing API).
    Safe to call from provisioning: failures here are logged and do not raise.
    """
    recipients = _admin_notification_recipients()
    if not recipients:
        return

    from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", None) or "").strip()
    if not from_email:
        logger.warning("ADMIN_EMAIL_NOTIFICATIONS set but DEFAULT_FROM_EMAIL is empty; skipping admin alert.")
        return

    subj = f"[Access code] Failed for booking {reference_id}"
    lines = [
        "Primary door code could not be created or confirmed on the lock via Seam.",
        "",
        f"Reference: {reference_id}",
        f"Guest: {(customer_name or '').strip() or '(none)'}",
        f"Guest email: {(customer_email or '').strip() or '(none)'}",
        "",
        f"Error: {error_message}",
    ]
    if error_body is not None:
        try:
            lines.extend(["", "Detail:", json.dumps(error_body, default=str, indent=2)[:8000]])
        except Exception:
            lines.extend(["", "Detail:", str(error_body)[:8000]])
    lines.extend(
        [
            "",
            "Guest outcome:",
            (
                "Backup PIN was emailed to the guest (SEAM_BACKUP_STATIC_CODE)."
                if guest_received_backup_pin
                else "No backup PIN configured — guest did NOT receive a door code in email."
            ),
        ]
    )
    body = "\n".join(lines)

    try:
        send_mail(
            subject=subj,
            message=body,
            from_email=from_email,
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send admin access-code alert for reference %s to %s",
            reference_id,
            recipients,
        )


def _fmt_code_dt(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    return str(value)


def _as_utc_aware(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=dt_timezone.utc)
        return val.astimezone(dt_timezone.utc)
    return None


def _booking_has_kids(booking: dict[str, Any] | None) -> bool:
    """True when booking payload includes one or more children (BookingPayloadSerializer.children)."""
    if not booking:
        return False
    raw = booking.get("children")
    if raw is None:
        return False
    try:
        return int(raw) >= 1
    except (TypeError, ValueError):
        return False


def format_access_codes_for_template(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows for SendGrid {{#each access_codes}} — strings only for reliable JSON encoding."""
    tz_label = getattr(settings, "BOOKING_TIMEZONE", "America/Chicago")
    rows: list[dict[str, Any]] = []
    for d in docs:
        su = _as_utc_aware(d.get("starts_at"))
        eu = _as_utc_aware(d.get("expires_at"))
        is_backup = str(d.get("seam_sync_status") or "") == "backup_static"
        rows.append(
            {
                "code": str(d.get("code") or ""),
                "lock_name": str(d.get("lock_name") or "Door"),
                "lock_location": str(d.get("lock_location") or ""),
                "starts_at": _fmt_code_dt(d.get("starts_at")),
                "expires_at": _fmt_code_dt(d.get("expires_at")),
                "starts_at_central": format_dt_central(su),
                "expires_at_central": format_dt_central(eu),
                "property_timezone": tz_label,
                "status": str(d.get("status") or ""),
                "is_backup_static": is_backup,
            }
        )
    return rows


def build_booking_dynamic_template_data(
    *,
    customer_name: str | None,
    reference_id: str,
    amount_cents: int,
    currency: str,
    receipt_url: str | None,
    payment_status: str,
    access_code_docs: list[dict[str, Any]] | None = None,
    booking: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Handlebars data for your SendGrid dynamic template (merge with template editor variables)."""
    name = (customer_name or "").strip() or "Guest"
    dollars = amount_cents / 100.0
    amount_display = f"{currency} {dollars:.2f}"
    brand = (getattr(settings, "SENDGRID_FROM_NAME", None) or "Team Kiwi").strip()
    codes = format_access_codes_for_template(access_code_docs or [])
    first_code = codes[0]["code"] if codes else ""
    codes_joined = ", ".join(c["code"] for c in codes if c.get("code"))
    has_kids = _booking_has_kids(booking)
    has_backup_access = any(c.get("is_backup_static") for c in codes)
    backup_lock_name = ""
    if has_backup_access:
        for c in codes:
            if c.get("is_backup_static"):
                backup_lock_name = str(c.get("lock_name") or "").strip()
                break

    base: dict[str, Any] = {
        "customer_name": name,
        "reference_id": reference_id,
        "amount_cents": amount_cents,
        "currency": currency,
        "amount_display": amount_display,
        "receipt_url": receipt_url or "",
        "payment_status": payment_status,
        "brand_name": brand,
        "access_codes": codes,
        "access_code": first_code,
        "access_codes_list": codes_joined,
        "has_access_codes": bool(codes),
        "booking_has_kids": has_kids,
        "bookingHasKids": has_kids,
        "has_backup_access": has_backup_access,
        "hasBackupAccess": has_backup_access,
        "backup_lock_name": backup_lock_name,
        "backupLockName": backup_lock_name,
        # camelCase aliases for templates that prefer them
        "customerName": name,
        "referenceId": reference_id,
        "amountCents": amount_cents,
        "amountDisplay": amount_display,
        "receiptUrl": receipt_url or "",
        "paymentStatus": payment_status,
        "brandName": brand,
        "accessCodes": codes,
        "accessCodesList": codes_joined,
        "hasAccessCodes": bool(codes),
        "booking_timezone": getattr(settings, "BOOKING_TIMEZONE", "America/Chicago"),
    }
    extra = _template_extra_from_env()
    merged = {**base, **extra}
    return merged


def send_dynamic_template_email(
    to_email: str,
    template_id: str,
    dynamic_template_data: dict[str, Any],
) -> None:
    """POST https://api.sendgrid.com/v3/mail/send with Bearer API key."""
    api_key = _sendgrid_api_key()
    if not api_key:
        raise ValueError("SENDGRID_API_KEY is not set.")

    from_email = (getattr(settings, "DEFAULT_FROM_EMAIL", None) or "").strip()
    if not from_email:
        raise ValueError("DEFAULT_FROM_EMAIL is not set.")

    from_name = (getattr(settings, "SENDGRID_FROM_NAME", None) or "Team Kiwi").strip()
    payload: dict[str, Any] = {
        "personalizations": [
            {
                "to": [{"email": to_email.strip()}],
                "dynamic_template_data": dynamic_template_data,
            }
        ],
        "from": {"email": from_email, "name": from_name},
        "template_id": template_id.strip(),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(SENDGRID_MAIL_SEND_URL, json=payload, headers=headers)
    if r.status_code >= 400:
        logger.error(
            "SendGrid template send failed: %s from=%s to=%s body=%s",
            r.status_code,
            from_email,
            to_email,
            r.text,
        )
        r.raise_for_status()


def collect_booking_confirmation_recipients(
    customer_email: str | None,
    booking: dict[str, Any] | None,
) -> list[str]:
    """
    Emails that should receive the booking confirmation (same content).

    Includes the payer ``customerEmail`` plus optional ``booking.guestEmails`` (list or
    comma/semicolon-separated string). Deduped case-insensitively; payer first when present.
    """
    seen: set[str] = set()
    ordered: list[str] = []

    def _add(raw: str | None) -> None:
        if not raw or not str(raw).strip():
            return
        e = str(raw).strip()
        key = e.lower()
        if key in seen:
            return
        seen.add(key)
        ordered.append(e)

    _add(customer_email)
    if not booking:
        return ordered
    extras = booking.get("guestEmails") or booking.get("guest_emails")
    if isinstance(extras, str):
        for part in extras.replace(";", ",").split(","):
            _add(part)
    elif isinstance(extras, list):
        for item in extras:
            if isinstance(item, str):
                _add(item)
    return ordered


def send_booking_confirmation_email(
    to_email: str,
    *,
    customer_name: str | None,
    reference_id: str,
    amount_cents: int,
    currency: str,
    receipt_url: str | None,
    payment_status: str,
    access_code_docs: list[dict[str, Any]] | None = None,
    booking: dict[str, Any] | None = None,
) -> None:
    """Notify guest after Square payment. Uses dynamic template when SENDGRID_DEFAULT_TEMPLATE_ID is set."""
    to_email = (to_email or "").strip()
    if not to_email:
        return

    template_id = (getattr(settings, "SENDGRID_DEFAULT_TEMPLATE_ID", None) or "").strip()
    codes = access_code_docs or []

    if template_id and _sendgrid_api_key():
        data = build_booking_dynamic_template_data(
            customer_name=customer_name,
            reference_id=reference_id,
            amount_cents=amount_cents,
            currency=currency,
            receipt_url=receipt_url,
            payment_status=payment_status,
            access_code_docs=codes,
            booking=booking,
        )
        try:
            send_dynamic_template_email(to_email, template_id, data)
        except Exception:
            logger.exception("Failed to send booking template email to %s", to_email)
        return

    if not _smtp_configured():
        return

    name = (customer_name or "").strip() or "Guest"
    dollars = amount_cents / 100.0
    lines = [
        f"Hi {name},",
        "",
        f"Thanks for your booking. Reference: {reference_id}",
        f"Amount: {currency} {dollars:.2f}",
        f"Payment status: {payment_status}",
    ]
    if receipt_url:
        lines.extend(["", f"Receipt: {receipt_url}"])
    if codes:
        lines.append("")
        if any(
            str(c.get("seam_sync_status") or "") == "backup_static"
            for c in (access_code_docs or [])
        ):
            lines.append(
                "BACKUP ENTRY: The timed door code could not be programmed automatically. "
                "Use the backup code below (same as your on-site backup lock). "
                "If anything is wrong, contact us with your reference number."
            )
        lines.append("Your door code(s):")
        for row in format_access_codes_for_template(codes):
            lines.append(
                f"  • {row['code']} ({row['lock_name']}) — active now through {row.get('expires_at_central') or row['expires_at']} (property time)"
            )
        if _booking_has_kids(booking):
            lines.extend(
                [
                    "",
                    "Children: This same door code may be used for children on your reservation. "
                    "Anyone under 18 must be accompanied by a responsible adult at all times on the property.",
                ]
            )
    lines.extend(["", "— Team Kiwi"])
    body = "\n".join(lines)

    try:
        send_mail(
            subject=f"Booking confirmed — {reference_id}",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[to_email],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send booking confirmation to %s", to_email)


def send_template_test_email(to_email: str) -> None:
    """Sample data for `manage.py sendgrid_test` when a template ID is configured."""
    template_id = (getattr(settings, "SENDGRID_DEFAULT_TEMPLATE_ID", None) or "").strip()
    if not template_id:
        raise ValueError("SENDGRID_DEFAULT_TEMPLATE_ID is not set.")
    data = build_booking_dynamic_template_data(
        customer_name="Test Guest",
        reference_id="TEST-REF-001",
        amount_cents=12345,
        currency="USD",
        receipt_url="https://example.com/receipt",
        payment_status="paid",
        access_code_docs=[
            {
                "code": "123456",
                "lock_name": "Front door",
                "lock_location": "",
                "starts_at": "2026-03-28T00:00:00+00:00",
                "expires_at": "2026-03-30T23:59:59+00:00",
                "status": "active",
            }
        ],
        booking={"children": 1, "totalCents": 12345},
    )
    send_dynamic_template_email(to_email, template_id, data)
