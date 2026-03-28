"""
Locks app entry point for Seam: wires Django settings to the shared HTTP client.

HTTP implementation lives in `services.seam_service` (reusable, testable).
"""

from __future__ import annotations

from django.conf import settings

from services.seam_service import DEFAULT_SEAM_BASE_URL, SeamService


def get_seam_service() -> SeamService:
    """Build a Seam client from environment-backed settings. Raises if the key is missing."""
    key = getattr(settings, "SEAM_API_KEY", "") or ""
    if not key.strip():
        raise ValueError(
            "SEAM_API_KEY is not set. Add it to .env (local) or Render environment variables."
        )
    base = (getattr(settings, "SEAM_API_BASE_URL", "") or "").strip() or DEFAULT_SEAM_BASE_URL
    return SeamService(api_key=key, base_url=base)
