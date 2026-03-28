"""Six-digit numeric lock codes (secrets-based)."""

from __future__ import annotations

import secrets


def generate_six_digit_code() -> str:
    """Return a string of exactly 6 decimal digits, e.g. '042891'."""
    n = secrets.randbelow(1_000_000)
    return f"{n:06d}"
