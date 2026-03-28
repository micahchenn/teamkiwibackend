"""Application MongoDB handle (named DB from settings, not necessarily URI default)."""

from __future__ import annotations

from django.conf import settings

from services.mongo_client import get_mongo_client


def get_mongo_database(**client_kwargs):
    return get_mongo_client(**client_kwargs)[settings.MONGO_DB_NAME]
