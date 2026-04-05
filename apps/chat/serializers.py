"""Chat serializers."""

from rest_framework import serializers

from apps.accounts.serializers import UserPublicSerializer

from .models import ChatRoom, Message


class MessageSerializer(serializers.ModelSerializer):
    sender = UserPublicSerializer(read_only=True)
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id", "sender", "message_type", "content",
            "image", "is_read", "read_at", "created_at", "is_mine",
        ]
        read_only_fields = fields

    def get_is_mine(self, obj: Message) -> bool:
        request = self.context.get("request")
        if request and request.user:
            return obj.sender == request.user
        return False


class SendMessageSerializer(serializers.Serializer):
    content = serializers.CharField(max_length=2000)


class ChatRoomSerializer(serializers.ModelSerializer):
    employer = UserPublicSerializer(read_only=True)
    worker = UserPublicSerializer(read_only=True)
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = [
            "id", "job", "employer", "worker",
            "is_active", "created_at",
            "last_message", "unread_count",
        ]

    def get_last_message(self, obj: ChatRoom) -> dict | None:
        msg = obj.messages.order_by("-created_at").first()
        if msg:
            return {
                "content": msg.content[:100],
                "sender_name": msg.sender.display_name if msg.sender else "System",
                "created_at": msg.created_at.isoformat(),
            }
        return None

    def get_unread_count(self, obj: ChatRoom) -> int:
        request = self.context.get("request")
        if not request:
            return 0
        return obj.messages.filter(is_read=False).exclude(sender=request.user).count()
