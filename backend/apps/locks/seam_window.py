"""
Seam access codes must use a window the device accepts. If the booking start is
already in the past when we call the API, Seam often returns 400 — so we clamp
`starts_at` to max(booking_start, now) before /access_codes/create.
"""

from __future__ import annotations

from datetime import datetime, timezone


def clamp_seam_window(
    starts_at: datetime,
    ends_at: datetime,
) -> tuple[datetime, datetime] | None:
    """
    Return (effective_start, ends_at) in UTC, or None if the window is already closed.
    """
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=timezone.utc)
    else:
        starts_at = starts_at.astimezone(timezone.utc)
    if ends_at.tzinfo is None:
        ends_at = ends_at.replace(tzinfo=timezone.utc)
    else:
        ends_at = ends_at.astimezone(timezone.utc)

    now = datetime.now(timezone.utc)
    effective = max(starts_at, now)
    if effective >= ends_at:
        return None
    return (effective, ends_at)
