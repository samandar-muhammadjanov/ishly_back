"""Core views - system-level endpoints."""

import logging

from django.core.cache import cache
from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """
    System health check endpoint.
    Returns status of database, cache, and application.
    Used by Docker, Kubernetes, and load balancers.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request: Request) -> Response:
        health = {
            "status": "healthy",
            "services": {},
        }

        # Check database
        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            health["services"]["database"] = "ok"
        except Exception as e:
            logger.error("Database health check failed: %s", e)
            health["services"]["database"] = "error"
            health["status"] = "degraded"

        # Check Redis cache
        try:
            cache.set("health_check", "ok", timeout=5)
            result = cache.get("health_check")
            health["services"]["cache"] = "ok" if result == "ok" else "error"
        except Exception as e:
            logger.error("Cache health check failed: %s", e)
            health["services"]["cache"] = "error"
            health["status"] = "degraded"

        status_code = 200 if health["status"] == "healthy" else 503
        return Response(health, status=status_code)
