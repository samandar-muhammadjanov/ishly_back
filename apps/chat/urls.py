"""Chat URL patterns."""

from django.urls import path
from .views import ChatRoomDetailView, MyChatRoomsView, SendMessageView

app_name = "chat"

urlpatterns = [
    path("", MyChatRoomsView.as_view(), name="room_list"),
    path("<uuid:room_id>/", ChatRoomDetailView.as_view(), name="room_detail"),
    path("<uuid:room_id>/messages/", SendMessageView.as_view(), name="send_message"),
]
