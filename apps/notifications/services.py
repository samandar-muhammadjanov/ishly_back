"""
Notifications service layer.
Orchestrates push delivery + DB record creation.
"""

import logging
from typing import Any

from apps.accounts.models import DeviceToken, User

from .models import Notification, NotificationType
from .push import get_push_provider

logger = logging.getLogger(__name__)


class NotificationService:
    """
    Send push notifications and persist them to the notification inbox.

    Design:
    - Always persist to DB (so users see history)
    - Attempt push delivery (failures are logged, not raised)
    - Batch-send when multiple recipients
    """

    @classmethod
    def send(
        cls,
        user: User,
        notification_type: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        send_push: bool = True,
    ) -> Notification:
        """
        Send a notification to a single user.

        1. Persist to DB
        2. Get active device tokens
        3. Send push (best-effort, won't raise on failure)
        """
        # Persist notification to DB
        notification = Notification.objects.create(
            user=user,
            notification_type=notification_type,
            title=title,
            body=body,
            data=data or {},
        )

        if send_push:
            cls._deliver_push(user, title, body, data)

        return notification

    @classmethod
    def send_bulk(
        cls,
        users: list[User],
        notification_type: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> int:
        """
        Send the same notification to multiple users.
        Returns count of notifications created.
        """
        notifications = [
            Notification(
                user=user,
                notification_type=notification_type,
                title=title,
                body=body,
                data=data or {},
            )
            for user in users
        ]
        Notification.objects.bulk_create(notifications, ignore_conflicts=True)

        # Collect all active device tokens
        tokens = list(
            DeviceToken.objects
            .filter(user__in=users, is_active=True)
            .values_list("token", flat=True)
        )
        if tokens:
            provider = get_push_provider()
            try:
                provider.send_to_tokens(tokens, title, body, data)
            except Exception as e:
                logger.error("Bulk push delivery failed: %s", e)

        return len(notifications)

    @classmethod
    def _deliver_push(
        cls,
        user: User,
        title: str,
        body: str,
        data: dict[str, Any] | None,
    ) -> None:
        """Best-effort push delivery — never raises."""
        tokens = list(
            DeviceToken.objects
            .filter(user=user, is_active=True)
            .values_list("token", flat=True)
        )

        if not tokens:
            logger.debug("No active device tokens for user %s", user.id)
            return

        provider = get_push_provider()
        try:
            if len(tokens) == 1:
                provider.send_to_token(tokens[0], title, body, data)
            else:
                provider.send_to_tokens(tokens, title, body, data)
        except Exception as e:
            logger.error("Push delivery failed for user %s: %s", user.id, e)

    # ------------------------------------------------------------------
    # Domain-specific notification helpers
    # ------------------------------------------------------------------

    @classmethod
    def notify_new_job(cls, job) -> None:
        """Notify nearby workers about a new job (bulk)."""
        from apps.accounts.models import User as UserModel

        # Get workers in the vicinity (rough match by DB count limit)
        workers = UserModel.objects.filter(
            role="worker",
            is_active=True,
            is_blocked=False,
        )[:500]  # Cap at 500 to avoid overloading queue

        if not workers:
            return

        cls.send_bulk(
            users=list(workers),
            notification_type=NotificationType.NEW_JOB,
            title="New job available! 💼",
            body=f"{job.title} — {job.address}",
            data={"job_id": str(job.id), "type": "new_job"},
        )

    @classmethod
    def notify_job_accepted(cls, job) -> None:
        """Notify employer that their job was accepted."""
        cls.send(
            user=job.employer,
            notification_type=NotificationType.JOB_ACCEPTED,
            title="Your job was accepted! ✅",
            body=f"{job.worker.display_name} accepted "{job.title}"",
            data={"job_id": str(job.id), "type": "job_accepted"},
        )

    @classmethod
    def notify_job_completed(cls, job) -> None:
        """Notify worker that payment has been released."""
        commission, worker_amount = __import__(
            "apps.core.utils", fromlist=["calculate_commission"]
        ).calculate_commission(job.price)

        cls.send(
            user=job.worker,
            notification_type=NotificationType.JOB_COMPLETED,
            title="Job completed — payment received! 💰",
            body=f"You earned {worker_amount / 100:,.0f} UZS for "{job.title}"",
            data={
                "job_id": str(job.id),
                "type": "job_completed",
                "amount": str(worker_amount),
            },
        )

    @classmethod
    def notify_payment_received(cls, user: User, amount: int) -> None:
        """Notify user of a confirmed deposit."""
        cls.send(
            user=user,
            notification_type=NotificationType.DEPOSIT_CONFIRMED,
            title="Deposit confirmed! 💳",
            body=f"{amount / 100:,.0f} UZS added to your wallet.",
            data={"type": "deposit", "amount": str(amount)},
        )
