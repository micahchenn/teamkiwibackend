import os

from .base import *  # noqa: F403

# true = Django’s detailed error page + traceback (default). false = generic 500 HTML (no settings dump).
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() in ("1", "true", "yes")
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# React (CRA :3000, Vite :5173). Add more in CORS_ALLOWED_ORIGINS via env if needed.
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
