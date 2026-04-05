"""
Accounts service layer.
All business logic for authentication, OTP, and user management lives here.
Views should be thin — delegate to services.
"""

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.exceptions import (
    ConflictException,
    OTPException,
    RateLimitException,
    UnauthorizedException,
)
from apps.core.utils import get_otp_rate_limit_key

from . import telegram_gateway
from .models import TelegramOTP, User

logger = logging.getLogger(__name__)


class OTPService:
    """
    Handles OTP sending and verification via Telegram Gateway.
    Replaces the old SMS-based flow: no code is generated locally —
    Telegram generates and delivers the OTP directly to the user's app.
    """

    RATE_LIMIT_COUNT: int = 3
    RATE_LIMIT_WINDOW: int = 600  # 10 minutes

    @classmethod
    def send_otp(cls, phone_number: str, ip_address: str | None = None) -> dict[str, Any]:
        """
        Send OTP via Telegram Gateway.

        Flow:
          1. Check rate limit (max 3 per phone per 10 minutes)
          2. Revoke and delete any existing active OTPs for this phone
          3. Call Telegram Gateway to send the message
          4. Persist the returned request_id in DB

        Returns dict with expires_in, phone_number, and message.
        Raises RateLimitException or ServiceUnavailableException on failure.
        """
        phone_str = str(phone_number)

        # Rate limit: max 3 requests per 10 minutes per phone
        rate_key = get_otp_rate_limit_key(phone_str)
        send_count = cache.get(rate_key, 0)
        if send_count >= cls.RATE_LIMIT_COUNT:
            logger.warning("Telegram OTP rate limit exceeded for %s", phone_str)
            raise RateLimitException(
                f"Too many OTP requests. Please wait before trying again."
            )

        # Revoke and delete any existing unused OTPs for this phone
        existing_otps = TelegramOTP.objects.filter(
            phone_number=phone_number, is_used=False
        )
        for otp in existing_otps:
            telegram_gateway.revoke_otp(otp.request_id)
        existing_otps.delete()

        # Send via Telegram Gateway (raises ServiceUnavailableException on failure)
        result = telegram_gateway.send_otp(phone_str)

        # Persist request_id for later verification
        TelegramOTP.objects.create(
            phone_number=phone_number,
            request_id=result["request_id"],
        )

        # Increment rate limit counter
        if send_count == 0:
            cache.set(rate_key, 1, timeout=cls.RATE_LIMIT_WINDOW)
        else:
            cache.incr(rate_key)

        logger.info("Telegram OTP sent to %s", phone_str)
        return {
            "expires_in": 300,
            "phone_number": phone_str,
            "message": "OTP sent via Telegram",
        }

    @classmethod
    def verify_otp(cls, phone_number: str, code: str) -> bool:
        """
        Verify an OTP code via Telegram Gateway.

        Flow:
          1. Load latest active TelegramOTP record for this phone
          2. Check expiry (300 seconds)
          3. Call Telegram Gateway to check the code
          4. Mark OTP as used on success

        Raises OTPException on any failure.
        """
        phone_str = str(phone_number)

        try:
            otp = TelegramOTP.objects.filter(
                phone_number=phone_number,
                is_used=False,
            ).latest("created_at")
        except TelegramOTP.DoesNotExist:
            raise OTPException("OTP not found. Please request a new one.")

        if otp.is_expired():
            raise OTPException("OTP expired. Please request a new one.")

        valid = telegram_gateway.verify_otp(otp.request_id, code)
        if not valid:
            raise OTPException("Invalid code.")

        otp.is_used = True
        otp.save(update_fields=["is_used"])

        logger.info("Telegram OTP verified for %s", phone_str)
        return True


class AuthService:
    """
    Handles user authentication and JWT token management.
    """

    @classmethod
    def authenticate_or_create(
        cls,
        phone_number: str,
        role: str = "worker",
    ) -> tuple["User", bool]:
        """
        Get existing user or create a new one after OTP verification.

        Returns:
            (user, is_new_user)
        """
        phone_str = str(phone_number)
        user, created = User.objects.get_or_create(
            phone_number=phone_str,
            defaults={
                "role": role,
                "is_active": True,
            },
        )

        if not created and user.is_blocked:
            raise UnauthorizedException("Your account has been suspended.")

        if not created and not user.is_active:
            raise UnauthorizedException("Your account is inactive.")

        # Update last seen
        user.last_seen = timezone.now()
        user.save(update_fields=["last_seen"])

        return user, created

    @classmethod
    def generate_tokens(cls, user: "User") -> dict[str, str]:
        """
        Generate JWT access and refresh tokens for a user.

        Adds custom claims: role, phone_number
        """
        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        refresh["phone_number"] = str(user.phone_number)

        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
        }

    @classmethod
    def logout(cls, refresh_token: str) -> None:
        """
        Blacklist the refresh token on logout.
        Subsequent requests with this token will be rejected.
        """
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except Exception as e:
            logger.warning("Failed to blacklist token: %s", e)
            raise UnauthorizedException("Invalid or expired token.")


class UserService:
    """
    Business logic for user profile management.
    """

    @classmethod
    def update_profile(cls, user: "User", data: dict[str, Any]) -> "User":
        """Update user profile fields."""
        for field, value in data.items():
            setattr(user, field, value)

        if user.name:
            user.is_profile_complete = True

        user.save()
        return user

    @classmethod
    def rate_user(
        cls,
        rater: "User",
        target_user: "User",
        rating: float,
        job_id: str,
        comment: str = "",
    ) -> None:
        """
        Rate a user after a completed job.
        Validates that the rater was involved in the job.
        """
        from apps.jobs.models import Job, JobStatus

        # Validate the job exists and is completed
        try:
            job = Job.objects.get(id=job_id, status=JobStatus.COMPLETED)
        except Job.DoesNotExist:
            from apps.core.exceptions import NotFoundException
            raise NotFoundException("Job not found or not completed.")

        # Validate rater was involved
        if rater not in (job.employer, job.worker):
            from apps.core.exceptions import ForbiddenException
            raise ForbiddenException("You were not involved in this job.")

        # Validate target was involved
        if target_user not in (job.employer, job.worker):
            from apps.core.exceptions import ForbiddenException
            raise ForbiddenException("Target user was not involved in this job.")

        # Validate rater is not rating themselves
        if rater == target_user:
            from apps.core.exceptions import ValidationException
            raise ValidationException("You cannot rate yourself.")

        from decimal import Decimal
        target_user.update_rating(Decimal(str(rating)))
        logger.info("User %s rated %s: %s", rater.id, target_user.id, rating)

    @classmethod
    def block_user(cls, user: "User", reason: str) -> None:
        """Admin action to block a user."""
        user.is_blocked = True
        user.block_reason = reason
        user.is_active = False
        user.save(update_fields=["is_blocked", "block_reason", "is_active"])
        logger.warning("User %s blocked. Reason: %s", user.id, reason)

    @classmethod
    def unblock_user(cls, user: "User") -> None:
        """Admin action to unblock a user."""
        user.is_blocked = False
        user.block_reason = ""
        user.is_active = True
        user.save(update_fields=["is_blocked", "block_reason", "is_active"])
        logger.info("User %s unblocked.", user.id)
