"""
Notification Celery tasks.
Async wrappers so views return immediately without waiting for push delivery.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    queue="notifications",
    max_retries=2,
    default_retry_delay=30,
    name="apps.notifications.tasks.notify_new_job_task",
)
def notify_new_job_task(self, job_id: str) -> None:
    """Notify workers about a newly created job."""
    try:
        from apps.jobs.models import Job
        from apps.notifications.services import NotificationService
        job = Job.objects.select_related("employer", "category").get(id=job_id)
        NotificationService.notify_new_job(job)
    except Exception as exc:
        logger.error("notify_new_job_task failed for job %s: %s", job_id, exc)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    queue="notifications",
    max_retries=2,
    default_retry_delay=30,
    name="apps.notifications.tasks.notify_job_accepted_task",
)
def notify_job_accepted_task(self, job_id: str) -> None:
    """Notify employer that their job was accepted by a worker."""
    try:
        from apps.jobs.models import Job
        from apps.notifications.services import NotificationService
        job = Job.objects.select_related("employer", "worker").get(id=job_id)
        NotificationService.notify_job_accepted(job)
    except Exception as exc:
        logger.error("notify_job_accepted_task failed for job %s: %s", job_id, exc)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    queue="notifications",
    max_retries=2,
    default_retry_delay=30,
    name="apps.notifications.tasks.notify_job_completed_task",
)
def notify_job_completed_task(self, job_id: str) -> None:
    """Notify worker of payment release after job completion."""
    try:
        from apps.jobs.models import Job
        from apps.notifications.services import NotificationService
        job = Job.objects.select_related("employer", "worker").get(id=job_id)
        NotificationService.notify_job_completed(job)
    except Exception as exc:
        logger.error("notify_job_completed_task failed for job %s: %s", job_id, exc)
        raise self.retry(exc=exc)


@shared_task(
    queue="notifications",
    name="apps.notifications.tasks.cleanup_expired_tokens",
)
def cleanup_expired_tokens() -> dict:
    """
    Monthly cleanup: deactivate device tokens that haven't been
    used in 90 days (stale / uninstalled apps).
    """
    from django.utils import timezone
    from datetime import timedelta
    from apps.accounts.models import DeviceToken

    cutoff = timezone.now() - timedelta(days=90)
    updated = DeviceToken.objects.filter(
        is_active=True,
        last_used_at__lt=cutoff,
    ).update(is_active=False)

    logger.info("Deactivated %d stale device tokens", updated)
    return {"deactivated": updated}
