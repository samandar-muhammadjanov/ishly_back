"""
Pagination classes for DRF views.
"""

from django.conf import settings
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardResultsPagination(PageNumberPagination):
    """
    Standard pagination that includes metadata in the response.

    Response format:
    {
        "success": true,
        "data": {
            "count": 100,
            "total_pages": 5,
            "current_page": 1,
            "next": "http://api/endpoint/?page=2",
            "previous": null,
            "results": [...]
        }
    }
    """

    page_size = settings.REST_FRAMEWORK.get("PAGE_SIZE", 20)
    page_size_query_param = "page_size"
    max_page_size = getattr(settings, "MAX_PAGE_SIZE", 100)
    page_query_param = "page"

    def get_paginated_response(self, data: list) -> Response:
        return Response(
            {
                "count": self.page.paginator.count,
                "total_pages": self.page.paginator.num_pages,
                "current_page": self.page.number,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema: dict) -> dict:
        return {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "example": 100},
                "total_pages": {"type": "integer", "example": 5},
                "current_page": {"type": "integer", "example": 1},
                "next": {"type": "string", "nullable": True},
                "previous": {"type": "string", "nullable": True},
                "results": schema,
            },
        }


class LargeResultsPagination(StandardResultsPagination):
    """Pagination for large datasets (e.g., admin views)."""

    page_size = 50
    max_page_size = 500


class SmallResultsPagination(StandardResultsPagination):
    """Pagination for small datasets (e.g., notifications)."""

    page_size = 10
    max_page_size = 50
