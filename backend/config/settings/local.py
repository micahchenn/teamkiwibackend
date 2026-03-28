from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# Local dev: allow all origins (tighten when testing real frontends)
CORS_ALLOW_ALL_ORIGINS = True
