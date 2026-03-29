"""
Guards before creating or emailing door access codes (Square payment flow).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from django.conf import settings

from apps.locks.booking_timezone import get_booking_zone, parse_visit_dates

logger = logging.getLogger(__name__)


def validate_booking_for_access_code(
    booking: dict[str, Any] | None,
    *,
    parsed_dates: tuple[date, date] | None = None,
) -> tuple[bool, str]:
    """
    Returns (ok, reason_code).

    * reason_code is a short machine string for logs; not shown to guests.
    """
    if not booking:
        return False, "missing_booking"

    dates = parsed_dates or parse_visit_dates(booking)
    if not dates:
        return False, "invalid_visit_dates"

    _visit_start, visit_end = dates
    span_days = (visit_end - visit_start).days + 1
    if span_days < 1:
        return False, "invalid_visit_span"

    max_span = max(1, int(getattr(settings, "BOOKING_MAX_VISIT_SPAN_DAYS", 90)))
    if span_days > max_span:
        logger.warning(
            "Rejected access code: visit span %s days exceeds max %s",
            span_days,
            max_span,
        )
        return False, "visit_span_exceeds_max"

    z = get_booking_zone()
    today_local = datetime.now(z).date()
    if visit_end < today_local:
        logger.info("Rejected access code: visit already ended (visitEnd=%s)", visit_end)
        return False, "visit_already_ended"

    return True, "ok"
