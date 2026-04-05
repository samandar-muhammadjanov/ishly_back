"""Notifications views."""

import logging

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import SmallResultsPagination

from .models import Notification
from .serializers import NotificationSerializer

logger = logging.getLogger(__name__)


class NotificationListView(APIView):
    """
    GET /notifications/
    Returns the authenticated user's notification inbox, newest first.
    Supports ?unread=true filter.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Notifications"], summary="List my notifications")
    def get(self, request: Request) -> Response:
        qs = Notification.objects.filter(user=request.user)

        if request.query_params.get("unread") == "true":
            qs = qs.filter(is_read=False)

        paginator = SmallResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = NotificationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class MarkNotificationReadView(APIView):
    """
    POST /notifications/{id}/read/
    Mark a single notification as read.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Notifications"], summary="Mark notification as read")
    def post(self, request: Request, notification_id: str) -> Response:
        try:
            notif = Notification.objects.get(id=notification_id, user=request.user)
            notif.mark_read()
            return Response({"message": "Marked as read."})
        except Notification.DoesNotExist:
            from apps.core.exceptions import NotFoundException
            raise NotFoundException("Notification not found.")


class MarkAllReadView(APIView):
    """
    POST /notifications/read-all/
    Mark all unread notifications as read.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Notifications"], summary="Mark all notifications as read")
    def post(self, request: Request) -> Response:
        from django.utils import timezone
        count = Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({"marked_read": count})


class UnreadCountView(APIView):
    """
    GET /notifications/unread-count/
    Returns the count of unread notifications.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Notifications"], summary="Get unread notification count")
    def get(self, request: Request) -> Response:
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread_count": count})
