"""User profile URL patterns."""

from django.urls import path

from apps.accounts.views import (
    MyProfileView,
    RateUserView,
    RegisterDeviceTokenView,
    UserDetailView,
)

app_name = "users"

urlpatterns = [
    path("me/", MyProfileView.as_view(), name="my_profile"),
    path("device-token/", RegisterDeviceTokenView.as_view(), name="device_token"),
    path("<uuid:user_id>/", UserDetailView.as_view(), name="user_detail"),
    path("<uuid:user_id>/rate/", RateUserView.as_view(), name="rate_user"),
]
