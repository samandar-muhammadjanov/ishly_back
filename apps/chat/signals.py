"""
Chat signals.
Auto-creates a ChatRoom when a job transitions to ACCEPTED status.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def setup_chat_signals():
    """
    Called from ChatConfig.ready().
    Late import avoids circular imports at startup.
    """
    from apps.jobs.models import Job, JobStatus

    @receiver(post_save, sender=Job)
    def create_chat_room_on_accept(sender, instance: Job, created: bool, **kwargs) -> None:
        """Create a ChatRoom automatically when a job is accepted."""
        if not created and instance.status == JobStatus.ACCEPTED and instance.worker:
            from apps.chat.models import ChatRoom
            room, was_created = ChatRoom.objects.get_or_create(
                job=instance,
                defaults={
                    "employer": instance.employer,
                    "worker": instance.worker,
                },
            )
            if was_created:
                # Post a system message to kick off the conversation
                from apps.chat.models import Message, MessageType
                Message.objects.create(
                    room=room,
                    sender=None,
                    message_type=MessageType.SYSTEM,
                    content=(
                        f'Job "{instance.title}" accepted. '
                        f"You can now chat with each other."
                    ),
                )
                logger.info("Chat room created for job %s", instance.id)
