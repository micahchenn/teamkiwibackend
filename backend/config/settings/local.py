import os

from .base import *  # noqa: F403

# true = Django’s detailed error page + traceback (default). false = generic 500 HTML (no settings dump).
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("1", "true", "yes")

# Merge .env ALLOWED_HOSTS (e.g. Render hostname) with local defaults.
_base_hosts = ["localhost", "127.0.0.1", "[::1]"]
_extra_hosts = os.environ.get("ALLOWED_HOSTS", "").strip()
if _extra_hosts:
    ALLOWED_HOSTS = list(
        dict.fromkeys(
            _base_hosts + [h.strip() for h in _extra_hosts.split(",") if h.strip()]
        )
    )
else:
    ALLOWED_HOSTS = _base_hosts

# React (CRA :3000, Vite :5173). Merge CORS_ALLOWED_ORIGINS from .env for deployed frontends.
CORS_ALLOW_ALL_ORIGINS = False
_base_cors = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_extra_cors = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
if _extra_cors:
    CORS_ALLOWED_ORIGINS = list(
        dict.fromkeys(
            _base_cors + [o.strip() for o in _extra_cors.split(",") if o.strip()]
        )
    )
else:
    CORS_ALLOWED_ORIGINS = _base_cors
