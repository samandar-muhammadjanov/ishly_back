"""Chat admin."""

from django.contrib import admin
from .models import ChatRoom, Message


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ["id", "job", "employer", "worker", "is_active", "created_at"]
    search_fields = ["employer__phone_number", "worker__phone_number"]
    raw_id_fields = ["job", "employer", "worker"]
    readonly_fields = ["id", "created_at"]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["room", "sender", "message_type", "content_preview", "is_read", "created_at"]
    list_filter = ["message_type", "is_read", "created_at"]
    search_fields = ["sender__phone_number", "content"]
    readonly_fields = ["id", "created_at"]

    def content_preview(self, obj):
        return obj.content[:60] + ("..." if len(obj.content) > 60 else "")
    content_preview.short_description = "Content"
