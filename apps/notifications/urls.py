"""Notifications URL patterns."""

from django.urls import path

from .views import MarkAllReadView, MarkNotificationReadView, NotificationListView, UnreadCountView

app_name = "notifications"

urlpatterns = [
    path("", NotificationListView.as_view(), name="list"),
    path("unread-count/", UnreadCountView.as_view(), name="unread_count"),
    path("read-all/", MarkAllReadView.as_view(), name="read_all"),
    path("<int:notification_id>/read/", MarkNotificationReadView.as_view(), name="mark_read"),
]
