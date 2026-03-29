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


def _first_name_prefix(customer_name: str | None, *, max_len: int = 7) -> str:
    """First word, letters only, capped at ``max_len``; ``Guest`` if empty."""
    if not customer_name or not str(customer_name).strip():
        return "Guest"
    first_token = str(customer_name).strip().split()[0]
    letters = "".join(c for c in first_token if c.isalpha())
    if not letters:
        return "Guest"
    chunk = letters[:max_len]
    return chunk[:1].upper() + chunk[1:].lower() if len(chunk) > 1 else chunk.upper()


def seam_access_code_name(
    code: str,
    *,
    lock_name_base: str | None = None,
    booking_reference: str | None = None,
    customer_name: str | None = None,
) -> str:
    """
    Human-readable name in Seam: ``{FirstName}-{reference_prefix}`` (e.g. ``Micah-4f7ffbd4``)
    when a booking reference exists — first name up to 7 letters, then ``-``, then the
    same stripped reference id as before (UUID segment before the first hyphen).

    If there is no reference, falls back to ``{6-digit PIN} {lock_name}`` for uniqueness.
    """
    label = _reference_label(booking_reference)
    if label:
        cust = _first_name_prefix(customer_name)
        return f"{cust}-{label}"
    base = (lock_name_base or "").strip() or "Access"
    return f"{code} {base}"
