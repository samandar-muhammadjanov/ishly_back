"""
Custom DRF renderer.
Wraps all successful responses in a consistent envelope.
"""

from typing import Any

from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response


class CustomJSONRenderer(JSONRenderer):
    """
    Wraps all API responses in a standard envelope:

    Success:
    {
        "success": true,
        "data": { ... }
    }

    Errors are handled by the exception handler in exceptions.py.
    """

    def render(
        self,
        data: Any,
        accepted_media_type: str | None = None,
        renderer_context: dict | None = None,
    ) -> bytes:
        if renderer_context is None:
            return super().render(data, accepted_media_type, renderer_context)

        response: Response | None = renderer_context.get("response")

        # Don't wrap error responses (already handled by exception_handler)
        if response is not None and response.status_code >= 400:
            return super().render(data, accepted_media_type, renderer_context)

        # Don't double-wrap if already has success key
        if isinstance(data, dict) and "success" in data:
            return super().render(data, accepted_media_type, renderer_context)

        # Wrap successful responses
        wrapped = {
            "success": True,
            "data": data,
        }

        return super().render(wrapped, accepted_media_type, renderer_context)
