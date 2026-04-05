"""
Chat REST views.
REST API for chat history (WebSocket handles real-time).
"""

import logging

from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ForbiddenException, NotFoundException
from apps.core.pagination import StandardResultsPagination

from .models import ChatRoom, Message
from .serializers import ChatRoomSerializer, MessageSerializer, SendMessageSerializer

logger = logging.getLogger(__name__)


class MyChatRoomsView(APIView):
    """GET /chat/ — list chat rooms for the authenticated user."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Chat"], summary="List my chat rooms")
    def get(self, request: Request) -> Response:
        from django.db.models import Q
        rooms = (
            ChatRoom.objects
            .filter(Q(employer=request.user) | Q(worker=request.user))
            .select_related("job", "employer", "worker")
            .prefetch_related("messages")
            .order_by("-created_at")
        )
        serializer = ChatRoomSerializer(rooms, many=True, context={"request": request})
        return Response(serializer.data)


class ChatRoomDetailView(APIView):
    """GET /chat/{room_id}/ — room info + paginated message history."""

    permission_classes = [IsAuthenticated]

    @extend_schema(tags=["Chat"], summary="Get chat room with message history")
    def get(self, request: Request, room_id: str) -> Response:
        room = self._get_room_or_404(room_id, request.user)
        messages = (
            Message.objects
            .filter(room=room)
            .select_related("sender")
            .order_by("-created_at")  # Newest first; client reverses for display
        )

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(messages, request)
        serializer = MessageSerializer(page, many=True, context={"request": request})
        return paginator.get_paginated_response(serializer.data)


class SendMessageView(APIView):
    """
    POST /chat/{room_id}/messages/
    Send a message via REST (fallback when WebSocket unavailable).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Chat"],
        summary="Send a chat message (REST fallback)",
        request=SendMessageSerializer,
    )
    def post(self, request: Request, room_id: str) -> Response:
        room = self._get_room_or_404(room_id, request.user)

        serializer = SendMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        message = Message.objects.create(
            room=room,
            sender=request.user,
            content=serializer.validated_data["content"],
        )

        return Response(
            MessageSerializer(message, context={"request": request}).data,
            status=201,
        )

    @staticmethod
    def _get_room_or_404(room_id: str, user) -> ChatRoom:
        try:
            room = ChatRoom.objects.get(id=room_id)
        except ChatRoom.DoesNotExist:
            raise NotFoundException("Chat room not found.")
        if not room.is_participant(user):
            raise ForbiddenException("You are not a participant of this chat room.")
        return room


# Shared helper
ChatRoomDetailView._get_room_or_404 = staticmethod(SendMessageView._get_room_or_404)
