"""
Accounts views.
Thin views that delegate all logic to services.
"""

import logging

from django.utils import timezone
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.generics import RetrieveUpdateAPIView, get_object_or_404
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import NotFoundException
from apps.core.permissions import IsActiveUser

from .models import User
from .serializers import (
    LogoutSerializer,
    RatingSerializer,
    RegisterDeviceTokenSerializer,
    SendOTPSerializer,
    UpdateProfileSerializer,
    UserProfileSerializer,
    UserPublicSerializer,
    VerifyOTPSerializer,
)
from .services import AuthService, OTPService, UserService

logger = logging.getLogger(__name__)


# ----------------------------
# Auth Views
# ----------------------------

class SendOTPView(APIView):
    """
    POST /auth/send-otp/

    Send OTP to a phone number.
    Rate limited to 5 requests per hour per phone.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "otp_send"

    @extend_schema(
        request=SendOTPSerializer,
        responses={
            200: OpenApiResponse(description="OTP sent successfully"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        },
        tags=["Authentication"],
        summary="Send OTP via SMS",
        examples=[
            OpenApiExample(
                "Send OTP",
                request_only=True,
                value={"phone_number": "+998901234567", "role": "worker"},
            ),
            OpenApiExample(
                "Success Response",
                response_only=True,
                value={
                    "success": True,
                    "data": {
                        "expires_in": 120,
                        "phone_number": "+998901234567",
                        "message": "OTP sent successfully",
                    },
                },
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = SendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data["phone_number"]
        ip = request.META.get("REMOTE_ADDR")

        result = OTPService.send_otp(phone_number, ip_address=ip)
        return Response(result, status=status.HTTP_200_OK)


class VerifyOTPView(APIView):
    """
    POST /auth/verify-otp/

    Verify OTP and return JWT tokens.
    Creates user account if first login.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "otp_verify"

    @extend_schema(
        request=VerifyOTPSerializer,
        tags=["Authentication"],
        summary="Verify OTP and get JWT tokens",
        examples=[
            OpenApiExample(
                "Verify OTP",
                request_only=True,
                value={"phone_number": "+998901234567", "code": "123456"},
            ),
            OpenApiExample(
                "Success Response",
                response_only=True,
                value={
                    "success": True,
                    "data": {
                        "access": "eyJ0eXAiOiJKV1QiLC...",
                        "refresh": "eyJ0eXAiOiJKV1QiLC...",
                        "is_new_user": False,
                        "user": {
                            "id": "550e8400-e29b-41d4-a716-446655440000",
                            "name": "Alisher Umarov",
                            "role": "worker",
                            "phone_number": "+998901234567",
                        },
                    },
                },
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone_number = serializer.validated_data["phone_number"]
        code = serializer.validated_data["code"]

        # Verify OTP (raises OTPException on failure)
        OTPService.verify_otp(phone_number, code)

        # Get or create user
        # Role defaults to worker for new users; existing users keep their role
        role = request.data.get("role", "worker")
        user, is_new = AuthService.authenticate_or_create(phone_number, role=role)

        # Generate JWT tokens
        tokens = AuthService.generate_tokens(user)

        return Response(
            {
                **tokens,
                "is_new_user": is_new,
                "user": UserProfileSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """
    POST /auth/logout/

    Blacklist the refresh token to log out.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=LogoutSerializer,
        tags=["Authentication"],
        summary="Logout and invalidate refresh token",
    )
    def post(self, request: Request) -> Response:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        AuthService.logout(serializer.validated_data["refresh"])

        return Response(
            {"message": "Logged out successfully."},
            status=status.HTTP_200_OK,
        )


# ----------------------------
# User Views
# ----------------------------

class MyProfileView(RetrieveUpdateAPIView):
    """
    GET  /users/me/  - Retrieve own profile
    PATCH /users/me/ - Update own profile
    """

    permission_classes = [IsAuthenticated, IsActiveUser]
    serializer_class = UserProfileSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_object(self) -> User:
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in ("PATCH", "PUT"):
            return UpdateProfileSerializer
        return UserProfileSerializer

    @extend_schema(tags=["Users"], summary="Get my profile")
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(tags=["Users"], summary="Update my profile")
    def patch(self, request: Request, *args, **kwargs) -> Response:
        return super().partial_update(request, *args, **kwargs)

    def put(self, request: Request, *args, **kwargs) -> Response:
        return super().partial_update(request, *args, **kwargs)


class UserDetailView(APIView):
    """
    GET /users/{id}/

    Public profile of any user.
    Phone number is masked for privacy.
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    @extend_schema(tags=["Users"], summary="Get user public profile")
    def get(self, request: Request, user_id: str) -> Response:
        user = get_object_or_404(User, id=user_id, is_active=True)
        serializer = UserPublicSerializer(user)
        return Response(serializer.data)


class RateUserView(APIView):
    """
    POST /users/{id}/rate/

    Rate a user after a completed job.
    Both employer and worker can rate each other.
    """

    permission_classes = [IsAuthenticated, IsActiveUser]

    @extend_schema(
        request=RatingSerializer,
        tags=["Users"],
        summary="Rate a user after job completion",
    )
    def post(self, request: Request, user_id: str) -> Response:
        target = get_object_or_404(User, id=user_id, is_active=True)

        serializer = RatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        UserService.rate_user(
            rater=request.user,
            target_user=target,
            rating=float(serializer.validated_data["rating"]),
            job_id=str(serializer.validated_data["job_id"]),
            comment=serializer.validated_data.get("comment", ""),
        )

        return Response(
            {"message": "Rating submitted successfully."},
            status=status.HTTP_200_OK,
        )


class RegisterDeviceTokenView(APIView):
    """
    POST /users/device-token/

    Register or update FCM push notification token.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=RegisterDeviceTokenSerializer,
        tags=["Users"],
        summary="Register FCM push notification token",
    )
    def post(self, request: Request) -> Response:
        serializer = RegisterDeviceTokenSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"message": "Device token registered."},
            status=status.HTTP_200_OK,
        )
