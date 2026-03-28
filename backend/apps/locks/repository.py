"""
Lock access codes in MongoDB (collection: lock_access_codes).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from django.conf import settings
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from services.code_generator import generate_six_digit_code
from services.mongo_db import get_mongo_database

logger = logging.getLogger(__name__)

COLLECTION = "lock_access_codes"
MAX_CODE_ATTEMPTS = 80
STATUS_ACTIVE = "active"
STATUS_EXPIRED = "expired"
STATUS_REVOKED = "revoked"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AccessCodeRepository:
    def __init__(self):
        self._db = get_mongo_database()
        self._col = self._db[COLLECTION]
        self._indexes_ensured = False

    def ensure_indexes(self) -> None:
        if self._indexes_ensured:
            return
        # Global unique 6-digit code (simple lookups; archive/delete old rows to reuse a code).
        self._col.create_index([("code", ASCENDING)], unique=True, name="uniq_code")
        self._col.create_index([("expires_at", ASCENDING)], name="expires_at_1")
        self._col.create_index([("device_id", ASCENDING)], name="device_id_1", sparse=True)
        self._indexes_ensured = True

    def create(
        self,
        *,
        expires_at: datetime,
        starts_at: datetime | None = None,
        device_id: str | None = None,
        lock_name: str | None = None,
        lock_location: str | None = None,
        booking_id: str | None = None,
        customer_name: str | None = None,
        customer_email: str | None = None,
        notes: str | None = None,
        seam_access_code_id: str | None = None,
    ) -> dict[str, Any]:
        self.ensure_indexes()
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        start = starts_at or _utcnow()
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if expires_at <= start:
            raise ValueError("expires_at must be after starts_at")

        now = _utcnow()
        if now >= expires_at:
            initial_status = STATUS_EXPIRED
        elif now < start:
            initial_status = "pending"
        else:
            initial_status = STATUS_ACTIVE

        last_err: Exception | None = None
        for _ in range(MAX_CODE_ATTEMPTS):
            code = generate_six_digit_code()
            doc = {
                "code": code,
                "status": initial_status,
                "starts_at": start,
                "expires_at": expires_at,
                "created_at": now,
                "updated_at": now,
                "device_id": device_id,
                "lock_name": lock_name,
                "lock_location": lock_location,
                "booking_id": booking_id,
                "customer_name": customer_name,
                "customer_email": customer_email,
                "notes": notes,
                "seam_access_code_id": seam_access_code_id,
            }
            try:
                result = self._col.insert_one(doc)
            except DuplicateKeyError as e:
                last_err = e
                continue
            doc["_id"] = result.inserted_id
            return self._serialize(doc)

        logger.error("Could not allocate unique 6-digit code after %s tries", MAX_CODE_ATTEMPTS)
        raise RuntimeError("Could not generate a unique code; try again.") from last_err

    def get_by_id(self, oid: str) -> dict[str, Any] | None:
        self.ensure_indexes()
        try:
            _id = ObjectId(oid)
        except InvalidId:
            return None
        doc = self._col.find_one({"_id": _id})
        if not doc:
            return None
        self._refresh_status_if_expired(doc)
        return self._serialize(doc)

    def patch_by_id(self, oid: str, fields: dict[str, Any]) -> bool:
        """Merge fields into document by string ObjectId."""
        self.ensure_indexes()
        try:
            _id = ObjectId(oid)
        except InvalidId:
            return False
        payload = {**fields, "updated_at": _utcnow()}
        r = self._col.update_one({"_id": _id}, {"$set": payload})
        return r.matched_count > 0

    def get_by_code(self, code: str) -> dict[str, Any] | None:
        self.ensure_indexes()
        if not code or len(code) != 6 or not code.isdigit():
            return None
        doc = self._col.find_one({"code": code})
        if not doc:
            return None
        self._refresh_status_if_expired(doc)
        return self._serialize(doc)

    def _refresh_status_if_expired(self, doc: dict[str, Any]) -> None:
        now = _utcnow()
        start = doc.get("starts_at")
        exp = doc.get("expires_at")
        if not start or not exp:
            return
        if now < start:
            resolved = "pending"
        elif now >= exp:
            resolved = STATUS_EXPIRED
        else:
            resolved = STATUS_ACTIVE
        if doc.get("status") == resolved:
            return
        if doc.get("status") in (STATUS_REVOKED,):
            return
        self._col.update_one(
            {"_id": doc["_id"]},
            {"$set": {"status": resolved, "updated_at": now}},
        )
        doc["status"] = resolved

    def _serialize(self, doc: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(doc["_id"]),
            "code": doc["code"],
            "status": doc["status"],
            "starts_at": doc["starts_at"],
            "expires_at": doc["expires_at"],
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"],
            "device_id": doc.get("device_id"),
            "lock_name": doc.get("lock_name"),
            "lock_location": doc.get("lock_location"),
            "booking_id": doc.get("booking_id"),
            "customer_name": doc.get("customer_name"),
            "customer_email": doc.get("customer_email"),
            "notes": doc.get("notes"),
            "seam_access_code_id": doc.get("seam_access_code_id"),
            "seam_sync_status": doc.get("seam_sync_status"),
            "seam_sync_error": doc.get("seam_sync_error"),
        }


def get_access_code_repository() -> AccessCodeRepository:
    return AccessCodeRepository()
