"""
Celery application configuration for GIG Marketplace.
"""

import os

from celery import Celery
from celery.schedules import crontab

# Set default Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("gig_marketplace")

# Load configuration from Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all installed apps
app.autodiscover_tasks()

# ----------------------------
# Periodic Tasks (Celery Beat)
# ----------------------------
app.conf.beat_schedule = {
    # Clean expired OTP codes every hour
    "cleanup-expired-otps": {
        "task": "apps.accounts.tasks.cleanup_expired_otps",
        "schedule": crontab(minute=0),  # Every hour
    },
    # Clean expired push notification tokens monthly
    "cleanup-notification-tokens": {
        "task": "apps.notifications.tasks.cleanup_expired_tokens",
        "schedule": crontab(0, 0, day_of_month="1"),  # First of each month
    },
}


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> None:
    """Debug task to verify Celery is working."""
    print(f"Request: {self.request!r}")
