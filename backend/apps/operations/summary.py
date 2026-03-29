"""Aggregate Mongo stats for the staff / operations console (no Django ORM)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from services.mongo_db import get_mongo_database


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def build_summary() -> dict[str, Any]:
    db = get_mongo_database()
    bookings_col = db["bookings"]
    locks_col = db["lock_access_codes"]

    bookings_total = bookings_col.count_documents({})
    codes_total = locks_col.count_documents({})

    def _count_by(field: str, collection) -> dict[str, int]:
        out: dict[str, int] = {}
        for row in collection.aggregate(
            [
                {"$group": {"_id": f"${field}", "n": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ]
        ):
            key = row["_id"]
            if key is None:
                key = "(none)"
            else:
                key = str(key)
            out[key] = int(row["n"])
        return out

    bookings_by_status = _count_by("payment_status", bookings_col)
    codes_by_status = _count_by("status", locks_col)

    recent_bookings: list[dict[str, Any]] = []
    for doc in bookings_col.find(
        {},
        {
            "reference_id": 1,
            "customer_name": 1,
            "customer_email": 1,
            "payment_status": 1,
            "amount_cents": 1,
            "currency": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(15):
        recent_bookings.append(
            {
                "reference_id": doc.get("reference_id"),
                "customer_name": doc.get("customer_name"),
                "customer_email": doc.get("customer_email"),
                "payment_status": doc.get("payment_status"),
                "amount_cents": doc.get("amount_cents"),
                "currency": doc.get("currency"),
                "created_at": _jsonable(doc.get("created_at")),
            }
        )

    recent_codes: list[dict[str, Any]] = []
    for doc in locks_col.find(
        {},
        {
            "code": 1,
            "status": 1,
            "lock_name": 1,
            "expires_at": 1,
            "booking_id": 1,
            "seam_access_code_id": 1,
            "created_at": 1,
        },
    ).sort("created_at", -1).limit(15):
        recent_codes.append(
            {
                "code": doc.get("code"),
                "status": doc.get("status"),
                "lock_name": doc.get("lock_name"),
                "expires_at": _jsonable(doc.get("expires_at")),
                "booking_id": doc.get("booking_id"),
                "seam_access_code_id": doc.get("seam_access_code_id"),
                "created_at": _jsonable(doc.get("created_at")),
            }
        )

    return {
        "bookings_total": bookings_total,
        "bookings_by_payment_status": bookings_by_status,
        "lock_codes_total": codes_total,
        "lock_codes_by_status": codes_by_status,
        "recent_bookings": recent_bookings,
        "recent_lock_codes": recent_codes,
    }
