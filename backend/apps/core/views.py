import logging

from django.conf import settings
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET

logger = logging.getLogger(__name__)


@require_GET
def api_root(_request):
    """GET / — avoids 404 when the base URL is opened; documents real API paths."""
    return JsonResponse(
        {
            "service": "Team Kiwi API",
            "health": "/api/health/",
            "square_config": "/api/square/config",
            "square_payments": "/api/square/payments",
        }
    )


@require_GET
def health_live(_request):
    """Liveness: process is up (use for load balancer / Render health checks)."""
    return JsonResponse({"status": "ok"})


@require_GET
def health_ready(_request):
    """
    Readiness: default DB and Redis reachable.
    Extend in later phases with MongoDB ping.
    """
    checks = {"database": False, "redis": False, "mongo": False}

    try:
        connection.ensure_connection()
        checks["database"] = True
    except Exception:
        logger.exception("Health check: database unavailable")

    try:
        import redis

        r = redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
        r.ping()
        checks["redis"] = True
    except Exception:
        logger.exception("Health check: redis unavailable")

    try:
        from services.mongo_client import get_mongo_client

        client = get_mongo_client(serverSelectionTimeoutMS=2000)
        client.admin.command("ping")
        checks["mongo"] = True
    except Exception:
        logger.exception("Health check: mongo unavailable")

    if all(checks.values()):
        return JsonResponse({"status": "ready", "checks": checks})
    return JsonResponse({"status": "not_ready", "checks": checks}, status=503)
