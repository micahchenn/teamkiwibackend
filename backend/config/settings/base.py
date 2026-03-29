"""
Base Django settings. Override via DJANGO_SETTINGS_MODULE (local vs production).
Render-friendly: no secrets here; use environment variables in production.py.
"""
import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


def _mongo_uri_from_env() -> str:
    """
    Full URI wins. Otherwise build Atlas-style URI from split credentials so
    special characters in passwords (e.g. &) are URL-encoded via quote_plus.
    """
    uri = os.environ.get("MONGO_URI", "").strip()
    if uri:
        return uri

    user = (os.environ.get("DATABASEUSERNAME") or os.environ.get("MONGO_USER") or "").strip()
    password = os.environ.get("DATABASEPASSWORD")
    if password is None:
        password = os.environ.get("MONGO_PASSWORD")
    password = password if isinstance(password, str) else ""

    host = (os.environ.get("MONGO_CLUSTER_HOST") or "").strip()
    db = (os.environ.get("MONGO_DB_NAME", "kiwiDB")).strip() or "kiwiDB"
    app_name = (os.environ.get("MONGO_APP_NAME", "TeamKiwi")).strip() or "TeamKiwi"

    if user and host:
        return (
            f"mongodb+srv://{quote_plus(user)}:{quote_plus(password)}@{host}/{db}"
            f"?retryWrites=true&w=majority&appName={quote_plus(app_name)}"
        )

    return "mongodb://localhost:27017/kiwiDB"

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env: backend/ first, then repo root (teamkiwibackend/.env) so either location works.
load_dotenv(BASE_DIR.parent / ".env")
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "dev-only-change-me-in-production-not-for-deploy",
)

DEBUG = False

ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "apps.core",
    "apps.bookings",
    "apps.locks",
    "apps.payments",
    "apps.webhooks",
    "apps.notifications",
    "apps.operations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Django default DB: lightweight metadata only. Domain data lives in MongoDB (later phases).
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- DRF (baseline; tighten per-view in later phases) ---
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
}

# CORS: restrict in production via env (comma-separated origins)
CORS_ALLOWED_ORIGINS: list[str] = []

# MongoDB (application data; repositories in later phases)
MONGO_URI = _mongo_uri_from_env()
# Used when MONGO_URI has no path (e.g. Atlas `...net/?appName=...`) — collections go here.
MONGO_DB_NAME = (os.environ.get("MONGO_DB_NAME", "kiwiDB") or "kiwiDB").strip() or "kiwiDB"

# Redis / Celery (horizontal scale: separate web and worker processes on Render)
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60 * 30  # hard cap for runaway tasks

# Integrations (placeholders for phase 2+)
SEAM_API_KEY = os.environ.get("SEAM_API_KEY", "")
# Default Seam lock UUID when POST body omits device_id (optional). Also accepts SEAM_DEVICE_ID.
SEAM_DEVICE_ID = (
    os.environ.get("SEAM_DEVICE_ID", "").strip()
    or os.environ.get("DEVICE_ID", "").strip()
    or None
)
# If set and SEAM_DEVICE_ID is empty, resolve device_id via Seam /devices/list (match display name).
SEAM_DEVICE_NAME = os.environ.get("SEAM_DEVICE_NAME", "").strip() or None
# When primary Seam PIN programming fails, email can include this 6-digit backup (must match the PIN on your backup lock in Seam; update env when admins change it).
SEAM_BACKUP_STATIC_CODE = os.environ.get("SEAM_BACKUP_STATIC_CODE", "").strip() or None
# Label for the backup lock (Seam display name / email copy), e.g. KIWIBACKUPKEY.
SEAM_BACKUP_LOCK_NAME = (os.environ.get("SEAM_BACKUP_LOCK_NAME", "") or "KIWIBACKUPKEY").strip() or "KIWIBACKUPKEY"
# Override only if Seam documents a different base (default: https://connect.getseam.com)
SEAM_API_BASE_URL = os.environ.get("SEAM_API_BASE_URL", "").strip()
# After access_codes/create, poll access_codes/get until status is ``set`` (PIN on physical lock).
try:
    SEAM_ACCESS_CODE_SET_TIMEOUT_SECONDS = float(
        os.environ.get("SEAM_ACCESS_CODE_SET_TIMEOUT_SECONDS", "120")
    )
except ValueError:
    SEAM_ACCESS_CODE_SET_TIMEOUT_SECONDS = 120.0
try:
    SEAM_ACCESS_CODE_POLL_INTERVAL_SECONDS = float(
        os.environ.get("SEAM_ACCESS_CODE_POLL_INTERVAL_SECONDS", "2")
    )
except ValueError:
    SEAM_ACCESS_CODE_POLL_INTERVAL_SECONDS = 2.0
SEAM_SKIP_ACCESS_CODE_SET_POLL = os.environ.get("SEAM_SKIP_ACCESS_CODE_SET_POLL", "").lower() in (
    "1",
    "true",
    "yes",
)
SQUARE_ACCESS_TOKEN = os.environ.get("SQUARE_ACCESS_TOKEN", "")
SQUARE_WEBHOOK_SECRET = os.environ.get("SQUARE_WEBHOOK_SECRET", "")
# sandbox | production — matches Square Developer Dashboard
SQUARE_ENVIRONMENT = os.environ.get("SQUARE_ENVIRONMENT", "sandbox").strip().lower()
# Web Payments SDK + Payments API (Locations → copy Location ID)
SQUARE_APPLICATION_ID = (
    os.environ.get("SQUARE_APPLICATION_ID", "").strip()
    or os.environ.get("REACT_APP_SQUARE_APPLICATION_ID", "").strip()
)
SQUARE_LOCATION_ID = os.environ.get("SQUARE_LOCATION_ID", "").strip()
SQUARE_API_VERSION = os.environ.get("SQUARE_API_VERSION", "2024-11-20").strip()

# SendGrid: API key used for v3 Mail Send (dynamic templates) and SMTP fallback.
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY", "").strip()
# Dynamic transactional template (Dashboard → Email API → Dynamic Templates). Starts with d-.
SENDGRID_DEFAULT_TEMPLATE_ID = (
    os.environ.get("SENDGRID_DEFAULT_TEMPLATE_ID", "").strip()
    or os.environ.get("SENDGRID_DEFUALT_TEMPLATE_ID", "").strip()  # common typo
)
SENDGRID_FROM_NAME = (os.environ.get("SENDGRID_FROM_NAME", "Team Kiwi") or "Team Kiwi").strip()
# Optional JSON merged into dynamic_template_data (e.g. {"site_url": "https://...", "phone": "..."}).
SENDGRID_TEMPLATE_EXTRA_JSON = os.environ.get("SENDGRID_TEMPLATE_EXTRA_JSON", "").strip()

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.sendgrid.net")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_USER", "apikey")
EMAIL_HOST_PASSWORD = SENDGRID_API_KEY or os.environ.get("EMAIL_PASS", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "true").lower() in ("1", "true", "yes")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "bookings@example.com")

# Comma-separated — alerts when Seam / door code provisioning fails (Square payment flow).
ADMIN_EMAIL_NOTIFICATIONS = os.environ.get("ADMIN_EMAIL_NOTIFICATIONS", "").strip()

# Property calendar for visitStart/visitEnd (day-pass / nightly stays). Affects lock expiry (end of last day in this zone).
BOOKING_TIMEZONE = (os.environ.get("BOOKING_TIMEZONE", "America/Chicago") or "America/Chicago").strip()
# Max inclusive calendar-day span (visitStart→visitEnd) before access codes are refused (fraud / typo guard).
try:
    BOOKING_MAX_VISIT_SPAN_DAYS = int(os.environ.get("BOOKING_MAX_VISIT_SPAN_DAYS", "90"))
except ValueError:
    BOOKING_MAX_VISIT_SPAN_DAYS = 90

# Staff / analytics API (GET /api/operations/summary/). Send header X-Operations-Key.
OPERATIONS_API_KEY = os.environ.get("OPERATIONS_API_KEY", "").strip()
