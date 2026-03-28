import os

from .base import *  # noqa: F403

DEBUG = False

_secret = os.environ.get("DJANGO_SECRET_KEY")
if not _secret:
    raise ValueError("DJANGO_SECRET_KEY must be set in production")
SECRET_KEY = _secret

_hosts = os.environ.get("ALLOWED_HOSTS", "").strip()
if not _hosts:
    raise ValueError("ALLOWED_HOSTS must be set in production (comma-separated)")
ALLOWED_HOSTS = [h.strip() for h in _hosts.split(",") if h.strip()]

# HTTPS (Render terminates TLS; trust X-Forwarded-Proto)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "true").lower() in (
    "1",
    "true",
    "yes",
)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS (optional; enable once domain is stable)
if os.environ.get("ENABLE_HSTS", "").lower() in ("1", "true", "yes"):
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "31536000"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# CORS
_cors = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors.split(",") if o.strip()]
CORS_ALLOW_ALL_ORIGINS = False
