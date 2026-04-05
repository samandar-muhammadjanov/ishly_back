"""
Shared utility functions used across all apps.
"""

import hashlib
import math
import random
import re
import string
from typing import Any

from django.conf import settings
from django.core.cache import cache


# ----------------------------
# OTP Utilities
# ----------------------------

def generate_otp(length: int | None = None) -> str:
    """Generate a numeric OTP of specified length."""
    otp_length = length or getattr(settings, "OTP_LENGTH", 6)
    if getattr(settings, "USE_FIXED_OTP", False):
        return getattr(settings, "DEV_FIXED_OTP", "123456")
    return "".join(random.choices(string.digits, k=otp_length))


def get_otp_cache_key(phone_number: str) -> str:
    """Generate a Redis key for storing OTP data."""
    hashed = hashlib.sha256(phone_number.encode()).hexdigest()[:16]
    return f"otp:{hashed}"


def get_otp_attempts_key(phone_number: str) -> str:
    """Generate a Redis key for tracking OTP verification attempts."""
    hashed = hashlib.sha256(phone_number.encode()).hexdigest()[:16]
    return f"otp_attempts:{hashed}"


def get_otp_rate_limit_key(phone_number: str) -> str:
    """Generate a Redis key for OTP send rate limiting."""
    hashed = hashlib.sha256(phone_number.encode()).hexdigest()[:16]
    return f"otp_rate:{hashed}"


# ----------------------------
# Cache Utilities
# ----------------------------

def make_cache_key(*parts: Any) -> str:
    """Build a consistent cache key from multiple parts."""
    return ":".join(str(p) for p in parts)


def invalidate_cache_pattern(pattern: str) -> int:
    """
    Invalidate all cache keys matching a pattern.
    Returns the number of keys deleted.
    """
    from django_redis import get_redis_connection
    try:
        conn = get_redis_connection("default")
        keys = conn.keys(f"*{settings.CACHES['default'].get('KEY_PREFIX', '')}*{pattern}*")
        if keys:
            conn.delete(*keys)
        return len(keys)
    except Exception:
        return 0


# ----------------------------
# Geo Utilities
# ----------------------------

def haversine_distance(
    lat1: float, lon1: float,
    lat2: float, lon2: float,
) -> float:
    """
    Calculate the great-circle distance (km) between two points on Earth.
    Uses the Haversine formula.
    """
    R = 6371.0  # Earth's radius in km

    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def bounding_box(lat: float, lon: float, radius_km: float) -> dict[str, float]:
    """
    Calculate a lat/lon bounding box for a given center point and radius.
    Used for fast pre-filtering before precise distance calculation.
    """
    lat_delta = radius_km / 111.0  # 1 degree lat ≈ 111 km
    lon_delta = radius_km / (111.0 * math.cos(math.radians(lat)))

    return {
        "lat_min": lat - lat_delta,
        "lat_max": lat + lat_delta,
        "lon_min": lon - lon_delta,
        "lon_max": lon + lon_delta,
    }


# ----------------------------
# Phone Number Utilities
# ----------------------------

def normalize_phone_number(phone: str) -> str:
    """
    Normalize a phone number to E.164 format.
    Strips spaces, dashes, and parentheses.
    """
    cleaned = re.sub(r"[\s\-\(\)]", "", phone)
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned
    return cleaned


# ----------------------------
# Pagination Utilities
# ----------------------------

def paginate_queryset(queryset, page: int, page_size: int) -> dict[str, Any]:
    """Simple manual pagination helper (use DRF pagination for views)."""
    total = queryset.count()
    offset = (page - 1) * page_size
    items = list(queryset[offset:offset + page_size])
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if page_size > 0 else 0,
        "has_next": offset + page_size < total,
        "has_prev": page > 1,
    }


# ----------------------------
# Financial Utilities
# ----------------------------

def calculate_commission(amount: int, percent: int | None = None) -> tuple[int, int]:
    """
    Calculate platform commission and worker payout.

    Args:
        amount: Total job price in smallest currency unit (e.g., tiyin)
        percent: Commission percentage (defaults to settings)

    Returns:
        Tuple of (commission_amount, worker_amount)
    """
    commission_percent = percent or getattr(settings, "PLATFORM_COMMISSION_PERCENT", 10)
    commission = int(amount * commission_percent / 100)
    worker_amount = amount - commission
    return commission, worker_amount
