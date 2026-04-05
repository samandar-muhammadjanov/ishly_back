"""
Celery tasks for the accounts app.
Handles async OTP sending and cleanup.
"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    queue="otp",
    max_retries=3,
    default_retry_delay=10,
    name="apps.accounts.tasks.send_otp_sms_task",
)
def send_otp_sms_task(self, phone_number: str, code: str) -> dict:
    """
    Send OTP SMS via configured provider.

    Retries up to 3 times with exponential backoff on failure.
    """
    from apps.notifications.sms import get_sms_provider

    try:
        provider = get_sms_provider()
        result = provider.send_otp(phone_number, code)

        logger.info(
            "OTP SMS sent to %s via %s",
            phone_number,
            provider.__class__.__name__,
        )
        return {"status": "sent", "phone": phone_number, "provider": result}

    except Exception as exc:
        logger.error(
            "Failed to send OTP to %s: %s",
            phone_number,
            str(exc),
            exc_info=True,
        )
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 10)


@shared_task(
    name="apps.accounts.tasks.cleanup_expired_otps",
    queue="default",
)
def cleanup_expired_otps() -> dict:
    """
    Periodic task: Remove expired OTP records from the database.
    Runs hourly via Celery Beat.
    """
    from apps.accounts.models import OTPCode

    cutoff = timezone.now()
    deleted_count, _ = OTPCode.objects.filter(
        expires_at__lt=cutoff,
        is_used=False,
    ).delete()

    logger.info("Cleaned up %d expired OTP records", deleted_count)
    return {"deleted": deleted_count}
