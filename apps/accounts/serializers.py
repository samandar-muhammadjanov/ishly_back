"""
Accounts serializers.
"""

from decimal import Decimal
from typing import Any

from django.conf import settings
from phonenumber_field.serializerfields import PhoneNumberField
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import DeviceToken, User


# ----------------------------
# Auth Serializers
# ----------------------------

class SendOTPSerializer(serializers.Serializer):
    """Request body for /auth/send-otp/"""

    phone_number = PhoneNumberField()
    role = serializers.ChoiceField(
        choices=["employer", "worker"],
        required=False,
        default="worker",
        help_text="Required only for new users. Ignored for existing users.",
    )


class VerifyOTPSerializer(serializers.Serializer):
    """Request body for /auth/verify-otp/"""

    phone_number = PhoneNumberField()
    code = serializers.CharField(
        min_length=4,
        max_length=10,
        help_text="OTP code received via SMS",
    )

    def validate_code(self, value: str) -> str:
        if not value.isdigit():
            raise serializers.ValidationError("OTP must contain only digits.")
        return value


class TokenResponseSerializer(serializers.Serializer):
    """Response shape for successful authentication."""

    access = serializers.CharField()
    refresh = serializers.CharField()
    user = serializers.SerializerMethodField()

    def get_user(self, obj: dict) -> dict:
        return obj.get("user", {})


class RefreshTokenSerializer(serializers.Serializer):
    """Request body for /auth/token/refresh/"""

    refresh = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    """Request body for /auth/logout/"""

    refresh = serializers.CharField()


# ----------------------------
# User Serializers
# ----------------------------

class UserPublicSerializer(serializers.ModelSerializer):
    """
    Public user profile - safe fields only, no sensitive data.
    Used when displaying worker/employer info to other users.
    """

    phone_number = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "name",
            "avatar",
            "role",
            "rating",
            "rating_count",
            "is_profile_complete",
            "phone_number",
            "created_at",
        ]
        read_only_fields = fields

    def get_phone_number(self, obj: User) -> str:
        return str(obj.phone_number)


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Full user profile - for the authenticated user themselves.
    Includes balance from related wallet.
    """

    balance = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "phone_number",
            "role",
            "name",
            "avatar",
            "bio",
            "rating",
            "rating_count",
            "balance",
            "is_profile_complete",
            "is_active",
            "created_at",
            "updated_at",
            "last_seen",
        ]
        read_only_fields = [
            "id", "phone_number", "role", "rating", "rating_count",
            "balance", "created_at", "updated_at",
        ]

    def get_balance(self, obj: User) -> int:
        try:
            return obj.wallet.balance
        except Exception:
            return 0

    def get_phone_number(self, obj: User) -> str:
        return str(obj.phone_number)


class UpdateProfileSerializer(serializers.ModelSerializer):
    """Request body for PATCH /users/me/"""

    class Meta:
        model = User
        fields = ["name", "avatar", "bio"]

    def validate_name(self, value: str) -> str:
        if len(value.strip()) < 2:
            raise serializers.ValidationError("Name must be at least 2 characters.")
        return value.strip()

    def update(self, instance: User, validated_data: dict[str, Any]) -> User:
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Auto-mark profile as complete if name is set
        if instance.name:
            instance.is_profile_complete = True

        instance.save()
        return instance


class RatingSerializer(serializers.Serializer):
    """Request body for POST /users/{id}/rate/"""

    rating = serializers.DecimalField(
        max_digits=3,
        decimal_places=1,
        min_value=Decimal("1.0"),
        max_value=Decimal("5.0"),
    )
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True)
    job_id = serializers.UUIDField(help_text="The job this rating is for")


# ----------------------------
# Device Token Serializers
# ----------------------------

class RegisterDeviceTokenSerializer(serializers.ModelSerializer):
    """Request body for POST /users/device-token/"""

    class Meta:
        model = DeviceToken
        fields = ["token", "platform"]

    def create(self, validated_data: dict[str, Any]) -> DeviceToken:
        user = self.context["request"].user
        token, created = DeviceToken.objects.update_or_create(
            token=validated_data["token"],
            defaults={
                "user": user,
                "platform": validated_data["platform"],
                "is_active": True,
            },
        )
        return token


# ----------------------------
# Custom JWT Token Serializer
# ----------------------------

class CustomTokenObtainSerializer(serializers.Serializer):
    """
    Placeholder - actual token generation is done in AuthService.
    This satisfies the SIMPLE_JWT setting requirement.
    """

    phone_number = PhoneNumberField()
    code = serializers.CharField()
