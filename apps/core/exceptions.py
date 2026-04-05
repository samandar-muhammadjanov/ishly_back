"""
Custom exceptions and DRF exception handler.
Ensures consistent error response format across all endpoints.
"""

import logging
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


# ----------------------------
# Custom Exception Classes
# ----------------------------

class GigBaseException(APIException):
    """Base exception for all GIG Marketplace exceptions."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "An error occurred."
    default_code = "error"


class ValidationException(GigBaseException):
    """Raised when input validation fails."""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "Validation failed."
    default_code = "validation_error"


class NotFoundException(GigBaseException):
    """Raised when a resource is not found."""
    status_code = status.HTTP_404_NOT_FOUND
    default_detail = "Resource not found."
    default_code = "not_found"


class ConflictException(GigBaseException):
    """Raised when a conflict occurs (e.g., duplicate resource)."""
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Resource conflict."
    default_code = "conflict"


class ForbiddenException(GigBaseException):
    """Raised when action is forbidden for the user's role."""
    status_code = status.HTTP_403_FORBIDDEN
    default_detail = "You do not have permission to perform this action."
    default_code = "forbidden"


class UnauthorizedException(GigBaseException):
    """Raised when authentication is required."""
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Authentication required."
    default_code = "unauthorized"


class RateLimitException(GigBaseException):
    """Raised when rate limit is exceeded."""
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_detail = "Rate limit exceeded. Try again later."
    default_code = "rate_limit_exceeded"


class InsufficientBalanceException(GigBaseException):
    """Raised when user has insufficient wallet balance."""
    status_code = status.HTTP_402_PAYMENT_REQUIRED
    default_detail = "Insufficient balance."
    default_code = "insufficient_balance"


class JobStateException(GigBaseException):
    """Raised when a job state transition is invalid."""
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Invalid job state transition."
    default_code = "invalid_job_state"


class OTPException(GigBaseException):
    """Raised for OTP-related errors."""
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "OTP error."
    default_code = "otp_error"


class ServiceUnavailableException(GigBaseException):
    """Raised when an external service is unavailable."""
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Service temporarily unavailable."
    default_code = "service_unavailable"


# ----------------------------
# DRF Custom Exception Handler
# ----------------------------

def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response:
    """
    Custom exception handler that ensures all errors follow a consistent format:

    {
        "success": false,
        "error": {
            "code": "error_code",
            "message": "Human readable message",
            "details": {}  // Optional extra info
        }
    }
    """
    # Let DRF handle standard exceptions first
    response = exception_handler(exc, context)

    # Log the exception
    request: Request = context.get("request")
    view = context.get("view")

    if response is None:
        # Handle Django's non-DRF exceptions
        if isinstance(exc, Http404):
            response = Response(status=status.HTTP_404_NOT_FOUND)
            exc = NotFoundException("Resource not found.")
        elif isinstance(exc, PermissionDenied):
            response = Response(status=status.HTTP_403_FORBIDDEN)
            exc = ForbiddenException("Permission denied.")
        elif isinstance(exc, ValidationError):
            response = Response(status=status.HTTP_400_BAD_REQUEST)
        else:
            logger.exception(
                "Unhandled exception in view",
                extra={
                    "view": view.__class__.__name__ if view else "unknown",
                    "path": request.path if request else "unknown",
                    "method": request.method if request else "unknown",
                },
                exc_info=exc,
            )
            response = Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    # Normalize the response data
    error_code = getattr(exc, "default_code", "error")
    if hasattr(exc, "detail"):
        detail = exc.detail
        if isinstance(detail, list):
            message = detail[0] if detail else str(exc)
        elif isinstance(detail, dict):
            # Extract the first error message from nested dict
            first_key = next(iter(detail))
            first_val = detail[first_key]
            message = first_val[0] if isinstance(first_val, list) else str(first_val)
        else:
            message = str(detail)
    else:
        message = str(exc)

    response.data = {
        "success": False,
        "error": {
            "code": error_code,
            "message": str(message),
            "details": response.data if isinstance(response.data, dict) else {},
        },
    }

    return response
