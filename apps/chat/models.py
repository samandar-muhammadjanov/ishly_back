"""
Chat models.
WebSocket-ready design using Django Channels.
One ChatRoom per Job — employer and worker communicate here.
"""

from django.db import models

from apps.accounts.models import User


class ChatRoom(models.Model):
    """
    One chat room per job, between employer and worker.
    Created when a worker accepts a job.
    """

    job = models.OneToOneField(
        "jobs.Job",
        on_delete=models.CASCADE,
        related_name="chat_room",
    )
    employer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="employer_chat_rooms"
    )
    worker = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="worker_chat_rooms"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "chat_rooms"
        verbose_name = "Chat Room"
        verbose_name_plural = "Chat Rooms"

    def __str__(self) -> str:
        return f"Chat: Job {self.job_id}"

    @property
    def channel_group_name(self) -> str:
        """Django Channels group name for this room."""
        return f"chat_{self.id}"

    def get_participants(self) -> list[User]:
        return [self.employer, self.worker]

    def is_participant(self, user: User) -> bool:
        return user in (self.employer, self.worker)


class MessageType(models.TextChoices):
    TEXT = "text", "Text"
    IMAGE = "image", "Image"
    SYSTEM = "system", "System Message"


class Message(models.Model):
    """
    Individual chat message. Immutable after creation.
    WebSocket consumers write to this model; REST API reads it.
    """

    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="sent_messages",
        null=True,
        blank=True,  # null for system messages
    )
    message_type = models.CharField(
        max_length=10,
        choices=MessageType.choices,
        default=MessageType.TEXT,
    )
    content = models.TextField(max_length=2000)
    image = models.ImageField(upload_to="chat/images/%Y/%m/", null=True, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "chat_messages"
        verbose_name = "Message"
        verbose_name_plural = "Messages"
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["room", "created_at"]),
            models.Index(fields=["room", "is_read"]),
        ]

    def __str__(self) -> str:
        sender = self.sender.display_name if self.sender else "System"
        return f"[{sender}] {self.content[:50]}"
