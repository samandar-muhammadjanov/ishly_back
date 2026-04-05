"""
Core middleware classes.
"""

import logging
import time
import uuid
from typing import Callable

from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    """
    Logs each request with timing, user info, and a unique request ID.
    Adds X-Request-ID header to every response for tracing.
    """

    def __init__(self, get_response: Callable) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Generate unique request ID
        request_id = str(uuid.uuid4())
        request.request_id = request_id  # type: ignore[attr-defined]

        start_time = time.monotonic()

        # Log request
        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "user_id": str(request.user.id) if hasattr(request, "user") and request.user.is_authenticated else "anonymous",
                "ip": self._get_client_ip(request),
            },
        )

        response = self.get_response(request)

        duration_ms = (time.monotonic() - start_time) * 1000

        # Log response
        logger.info(
            "Request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )

        # Add tracking headers
        response["X-Request-ID"] = request_id
        response["X-Response-Time"] = f"{duration_ms:.2f}ms"

        return response

    @staticmethod
    def _get_client_ip(request: HttpRequest) -> str:
        """Extract real client IP, handling reverse proxies."""
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        if x_forwarded_for:
            return x_forwarded_for.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "unknown")
