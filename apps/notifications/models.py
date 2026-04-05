"""
Notifications models.
Persists notification history for each user (in-app notification inbox).
"""

import uuid

from django.db import models

from apps.accounts.models import User


class NotificationType(models.TextChoices):
    NEW_JOB = "new_job", "New Job Available"
    JOB_ACCEPTED = "job_accepted", "Job Accepted"
    JOB_STARTED = "job_started", "Job Started"
    JOB_COMPLETED = "job_completed", "Job Completed"
    JOB_CANCELLED = "job_cancelled", "Job Cancelled"
    PAYMENT_RECEIVED = "payment_received", "Payment Received"
    DEPOSIT_CONFIRMED = "deposit_confirmed", "Deposit Confirmed"
    SYSTEM = "system", "System Message"


class Notification(models.Model):
    """
    Persisted notification record for a user's notification inbox.
    Created when a push notification is sent so users can
    see notification history in the app even after dismissing.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        db_index=True,
    )
    title = models.CharField(max_length=200)
    body = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "notifications_notifications"
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read"]),
            models.Index(fields=["user", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"[{self.notification_type}] {self.title} → {self.user.phone_number}"

    def mark_read(self) -> None:
        from django.utils import timezone
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])
