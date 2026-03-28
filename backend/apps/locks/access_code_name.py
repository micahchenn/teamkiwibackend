"""Seam / Kwikset access code naming (display name on device)."""


def _reference_label(booking_reference: str | None) -> str | None:
    """First segment of a UUID-style id (text before the first ``-``), or the whole id if no hyphen."""
    if not booking_reference:
        return None
    ref = booking_reference.strip()
    if not ref:
        return None
    if "-" in ref:
        part = ref.split("-", 1)[0].strip()
        return part or None
    return ref


def seam_access_code_name(
    code: str,
    *,
    lock_name_base: str | None = None,
    booking_reference: str | None = None,
) -> str:
    """
    Kwikset: first 14 characters of the access code *name* must be unique on the device.

    Use ``{6-digit PIN} {reference_prefix}`` where ``reference_prefix`` is the part of the
    booking/reference id before the first ``-`` (e.g. UUID segment ``43ff525c``), so names
    stay short and unique. If there is no reference, fall back to ``{code} {lock_name}``.
    """
    label = _reference_label(booking_reference)
    if label:
        return f"{code} {label}"
    base = (lock_name_base or "").strip() or "Access"
    return f"{code} {base}"
