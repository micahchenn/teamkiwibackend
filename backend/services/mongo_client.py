"""
Shared PyMongo client factory for Atlas + local MongoDB.

Atlas recommends Server API version 1 for mongodb+srv connections.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from pymongo import MongoClient
from pymongo.server_api import ServerApi


def get_mongo_client(**kwargs: Any) -> MongoClient:
    """
    Build a MongoClient from settings.MONGO_URI.
    Uses ServerApi('1') for mongodb+srv (Atlas) URIs.
    """
    uri = (getattr(settings, "MONGO_URI", None) or "").strip()
    if not uri:
        raise ValueError(
            "MONGO_URI is not configured (or build it from DATABASEUSERNAME, "
            "DATABASEPASSWORD, MONGO_CLUSTER_HOST — see settings)."
        )

    opts: dict[str, Any] = {"serverSelectionTimeoutMS": 10000}
    if uri.startswith("mongodb+srv://"):
        opts["server_api"] = ServerApi("1")
    opts.update(kwargs)
    return MongoClient(uri, **opts)
