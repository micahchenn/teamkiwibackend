"""
Booking stay dates are calendar days in a property timezone (default US Central).
Visit end = last night of stay → code expires at end of that calendar day in that zone.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone as dt_utc
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings


def get_booking_zone() -> ZoneInfo:
    name = getattr(settings, "BOOKING_TIMEZONE", None) or "America/Chicago"
    return ZoneInfo(str(name).strip() or "America/Chicago")


def visit_end_to_expires_utc(visit_end: date) -> datetime:
    """Last instant of ``visit_end`` on the property clock, stored as UTC for Mongo/Seam."""
    z = get_booking_zone()
    local_end = datetime.combine(visit_end, time(23, 59, 59, 999999), tzinfo=z)
    return local_end.astimezone(dt_utc.utc)


def utc_now() -> datetime:
    return datetime.now(dt_utc.utc)


def format_dt_central(dt: datetime | None) -> str:
    """Human-readable for emails (e.g. ``Mar 28, 2026 11:59 PM CDT``)."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_utc.utc)
    z = get_booking_zone()
    local = dt.astimezone(z)
    return local.strftime("%b %d, %Y %I:%M %p %Z")


def parse_visit_dates(booking: dict[str, Any] | None) -> tuple[date, date] | None:
    """Read visitStart / visitEnd as calendar dates (DRF DateField or ISO strings)."""
    if not booking:
        return None
    raw_s = booking.get("visitStart") or booking.get("visit_start")
    raw_e = booking.get("visitEnd") or booking.get("visit_end")
    ds = _coerce_date(raw_s)
    de = _coerce_date(raw_e)
    if ds is None or de is None:
        return None
    if de < ds:
        return None
    return (ds, de)


def _coerce_date(v: Any) -> date | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # YYYY-MM-DD
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    return None
