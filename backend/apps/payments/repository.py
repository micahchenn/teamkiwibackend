"""
MongoDB: `bookings` — checkout / payment records keyed by reference_id (UUID from frontend).
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING

from services.mongo_db import get_mongo_database


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _bson_safe_value(obj: Any) -> Any:
    """PyMongo encodes datetime; plain date and mixed nested dicts must be normalized."""
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            return obj.replace(tzinfo=timezone.utc)
        return obj.astimezone(timezone.utc)
    if isinstance(obj, date):
        return datetime.combine(obj, time.min, tzinfo=timezone.utc)
    if isinstance(obj, dict):
        return {k: _bson_safe_value(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_bson_safe_value(v) for v in obj]
    return obj


COLLECTION = "bookings"


class BookingRepository:
    def __init__(self):
        self._db = get_mongo_database()
        self._col = self._db[COLLECTION]
        self._indexes = False

    def ensure_indexes(self) -> None:
        if self._indexes:
            return
        self._col.create_index([("reference_id", ASCENDING)], unique=True, name="uniq_reference_id")
        self._col.create_index([("square_payment_id", ASCENDING)], sparse=True, name="square_payment_id_1")
        self._col.create_index([("created_at", ASCENDING)], name="created_at_1")
        self._indexes = True

    def upsert_payment_result(
        self,
        *,
        reference_id: str,
        customer_name: str | None,
        customer_email: str | None,
        customer_phone: str | None,
        booking: dict[str, Any] | None,
        amount_cents: int,
        currency: str,
        note: str | None,
        square_payment_id: str | None,
        square_status: str | None,
        receipt_url: str | None,
        payment_status: str,
    ) -> dict[str, Any]:
        self.ensure_indexes()
        now = _utcnow()
        safe_booking = _bson_safe_value(booking) if booking else {}
        doc = {
            "reference_id": reference_id,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "customer_phone": customer_phone,
            "booking": safe_booking,
            "amount_cents": amount_cents,
            "currency": currency,
            "note": note,
            "payment_status": payment_status,
            "square_payment_id": square_payment_id,
            "square_status": square_status,
            "receipt_url": receipt_url,
            "updated_at": now,
        }
        self._col.update_one(
            {"reference_id": reference_id},
            {
                "$set": doc,
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )
        row = self._col.find_one({"reference_id": reference_id})
        return self._serialize(row) if row else doc

    def get_by_reference_id(self, reference_id: str) -> dict[str, Any] | None:
        self.ensure_indexes()
        row = self._col.find_one({"reference_id": reference_id})
        return self._serialize(row) if row else None

    def _serialize(self, row: dict[str, Any]) -> dict[str, Any]:
        out = {
            "id": str(row["_id"]),
            "reference_id": row.get("reference_id"),
            "customer_name": row.get("customer_name"),
            "customer_email": row.get("customer_email"),
            "customer_phone": row.get("customer_phone"),
            "booking": row.get("booking") or {},
            "amount_cents": row.get("amount_cents"),
            "currency": row.get("currency"),
            "note": row.get("note"),
            "payment_status": row.get("payment_status"),
            "square_payment_id": row.get("square_payment_id"),
            "square_status": row.get("square_status"),
            "receipt_url": row.get("receipt_url"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }
        return out


def get_booking_repository() -> BookingRepository:
    return BookingRepository()
