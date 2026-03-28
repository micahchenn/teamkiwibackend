import os
from urllib.parse import urlparse

from .base import *  # noqa: F403

DEBUG = False

_secret = os.environ.get("DJANGO_SECRET_KEY")
if not _secret:
    raise ValueError("DJANGO_SECRET_KEY must be set in production")
SECRET_KEY = _secret

# ALLOWED_HOSTS: comma-separated env, plus Render’s public hostname from RENDER_EXTERNAL_URL
# (set automatically on web services — see https://render.com/docs/environment-variables).
# This avoids DisallowedHost when ALLOWED_HOSTS was not copied into the dashboard.
_raw_hosts = os.environ.get("ALLOWED_HOSTS", "").strip()
ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]
_render_url = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
if _render_url:
    _render_hostname = urlparse(_render_url).hostname
    if _render_hostname and _render_hostname not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_render_hostname)
if not ALLOWED_HOSTS:
    if os.environ.get("RENDER", "").lower() in ("1", "true", "yes"):
        # Celery workers often have no RENDER_EXTERNAL_URL; Django still requires a value.
        ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
    else:
        raise ValueError("ALLOWED_HOSTS must be set in production (comma-separated)")

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
