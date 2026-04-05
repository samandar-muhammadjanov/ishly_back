"""
Chat WebSocket consumer.
Uses Django Channels for real-time bidirectional messaging.
Handles: connect, disconnect, receive message, broadcast to room group.

WebSocket URL: ws://host/ws/chat/{room_id}/
Authorization:  ?token=<JWT access token>  (in query string)
"""

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

try:
    from channels.db import database_sync_to_async
    from channels.generic.websocket import AsyncWebsocketConsumer

    class ChatConsumer(AsyncWebsocketConsumer):
        """
        Async WebSocket consumer for per-job chat rooms.

        Message format (client → server):
        {
            "type": "chat_message",
            "content": "Hello!"
        }

        Broadcast format (server → client):
        {
            "type": "chat_message",
            "message": {
                "id": "uuid",
                "sender_id": "uuid",
                "sender_name": "Alisher",
                "content": "Hello!",
                "created_at": "2024-01-01T10:00:00Z"
            }
        }
        """

        async def connect(self) -> None:
            self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
            self.room_group_name = f"chat_{self.room_id}"
            self.user = self.scope.get("user")

            # Reject unauthenticated connections
            if not self.user or not self.user.is_authenticated:
                await self.close(code=4001)
                return

            # Validate room access
            room = await self._get_room(self.room_id)
            if room is None or not room.is_participant(self.user):
                await self.close(code=4003)
                return

            self.room = room

            # Join the channel group
            await self.channel_layer.group_add(
                self.room_group_name, self.channel_name
            )
            await self.accept()

            logger.info("WebSocket connect: user=%s, room=%s", self.user.id, self.room_id)

        async def disconnect(self, close_code: int) -> None:
            if hasattr(self, "room_group_name"):
                await self.channel_layer.group_discard(
                    self.room_group_name, self.channel_name
                )
            logger.info("WebSocket disconnect: code=%s", close_code)

        async def receive(self, text_data: str | None = None, bytes_data=None) -> None:
            """Handle incoming message from WebSocket client."""
            if not text_data:
                return
            try:
                data = json.loads(text_data)
            except json.JSONDecodeError:
                await self.send_error("Invalid JSON")
                return

            msg_type = data.get("type")
            if msg_type == "chat_message":
                await self.handle_chat_message(data)
            elif msg_type == "typing":
                await self.handle_typing(data)
            elif msg_type == "read_receipt":
                await self.handle_read_receipt(data)

        async def handle_chat_message(self, data: dict[str, Any]) -> None:
            content = data.get("content", "").strip()
            if not content:
                return
            if len(content) > 2000:
                await self.send_error("Message too long (max 2000 chars)")
                return

            # Persist message to DB
            message = await self._save_message(content)

            # Broadcast to all room participants
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat_message",
                    "message": {
                        "id": str(message.id),
                        "sender_id": str(self.user.id),
                        "sender_name": self.user.display_name,
                        "content": message.content,
                        "created_at": message.created_at.isoformat(),
                    },
                },
            )

        async def handle_typing(self, data: dict[str, Any]) -> None:
            """Broadcast typing indicator (not persisted)."""
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_indicator",
                    "user_id": str(self.user.id),
                    "user_name": self.user.display_name,
                    "is_typing": data.get("is_typing", False),
                },
            )

        async def handle_read_receipt(self, data: dict[str, Any]) -> None:
            """Mark messages as read."""
            await self._mark_messages_read()
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "read_receipt",
                    "user_id": str(self.user.id),
                },
            )

        # ------------------------------------------------------------------
        # Channel layer event handlers (group_send → these methods)
        # ------------------------------------------------------------------

        async def chat_message(self, event: dict) -> None:
            await self.send(text_data=json.dumps({
                "type": "chat_message",
                "message": event["message"],
            }))

        async def typing_indicator(self, event: dict) -> None:
            # Don't send typing indicator back to the sender
            if event["user_id"] != str(self.user.id):
                await self.send(text_data=json.dumps({
                    "type": "typing",
                    "user_id": event["user_id"],
                    "user_name": event["user_name"],
                    "is_typing": event["is_typing"],
                }))

        async def read_receipt(self, event: dict) -> None:
            await self.send(text_data=json.dumps({
                "type": "read_receipt",
                "user_id": event["user_id"],
            }))

        # ------------------------------------------------------------------
        # DB helpers (sync → async via database_sync_to_async)
        # ------------------------------------------------------------------

        @database_sync_to_async
        def _get_room(self, room_id: str):
            from .models import ChatRoom
            try:
                return ChatRoom.objects.select_related("employer", "worker").get(
                    id=room_id, is_active=True
                )
            except ChatRoom.DoesNotExist:
                return None

        @database_sync_to_async
        def _save_message(self, content: str):
            from .models import Message, MessageType
            return Message.objects.create(
                room=self.room,
                sender=self.user,
                message_type=MessageType.TEXT,
                content=content,
            )

        @database_sync_to_async
        def _mark_messages_read(self) -> None:
            from django.utils import timezone
            from .models import Message
            Message.objects.filter(
                room=self.room,
                is_read=False,
            ).exclude(sender=self.user).update(is_read=True, read_at=timezone.now())

        async def send_error(self, message: str) -> None:
            await self.send(text_data=json.dumps({
                "type": "error",
                "message": message,
            }))

except ImportError:
    # Django Channels not installed — define a placeholder
    class ChatConsumer:  # type: ignore[no-redef]
        """Placeholder when Django Channels is not installed."""
        pass
