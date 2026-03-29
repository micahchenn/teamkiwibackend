"""
Resolve Seam ``device_id`` from Django settings (UUID and/or display name).
"""

from __future__ import annotations

import logging

from django.conf import settings

from apps.locks.seam import get_seam_service

logger = logging.getLogger(__name__)

_cached_name: str | None = None
_cached_id: str | None = None


def resolve_seam_device_id_for_payment() -> str | None:
    """
    Prefer explicit ``SEAM_DEVICE_ID`` / ``DEVICE_ID``; otherwise resolve
    ``SEAM_DEVICE_NAME`` (e.g. ``Grape``) via Seam ``/devices/list``.
    """
    raw = getattr(settings, "SEAM_DEVICE_ID", None)
    if raw is not None:
        s = str(raw).strip()
        if s:
            return s

    name = getattr(settings, "SEAM_DEVICE_NAME", None) or ""
    name = str(name).strip()
    if not name:
        return None

    global _cached_name, _cached_id
    if _cached_name == name and _cached_id:
        return _cached_id

    try:
        seam = get_seam_service()
    except ValueError as e:
        logger.warning("Cannot resolve SEAM_DEVICE_NAME: %s", e)
        return None

    did = seam.find_device_id_by_display_name(name)
    if did:
        _cached_name = name
        _cached_id = did
        logger.info("Resolved SEAM_DEVICE_NAME=%r to device_id=%s", name, did)
    return did
