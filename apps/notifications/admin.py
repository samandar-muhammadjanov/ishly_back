"""Notifications admin."""

from django.contrib import admin

from .models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["title", "user", "notification_type", "is_read", "created_at"]
    list_filter = ["notification_type", "is_read", "created_at"]
    search_fields = ["user__phone_number", "title"]
    readonly_fields = ["id", "created_at", "read_at"]
    ordering = ["-created_at"]
