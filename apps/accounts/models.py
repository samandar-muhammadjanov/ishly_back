"""
Accounts models.
Custom User model with phone-number auth, roles, wallet balance, and rating.
"""

from decimal import Decimal

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from phonenumber_field.modelfields import PhoneNumberField


class UserRole(models.TextChoices):
    EMPLOYER = "employer", "Employer"
    WORKER = "worker", "Worker"


class UserManager(BaseUserManager):
    """Custom manager for phone-number-based authentication."""

    def create_user(
        self,
        phone_number: str,
        role: str = UserRole.WORKER,
        password: str | None = None,
        **extra_fields,
    ) -> "User":
        if not phone_number:
            raise ValueError("Phone number is required.")
        user = self.model(phone_number=phone_number, role=role, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number: str, password: str, **extra_fields) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("role", UserRole.EMPLOYER)

        if not extra_fields.get("is_staff"):
            raise ValueError("Superuser must have is_staff=True.")
        if not extra_fields.get("is_superuser"):
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(phone_number, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Custom User model using phone number as the unique identifier.

    Roles:
      - employer: Posts jobs, manages budget
      - worker:   Discovers and accepts jobs
    """

    phone_number = PhoneNumberField(unique=True, db_index=True)
    role = models.CharField(
        max_length=10,
        choices=UserRole.choices,
        default=UserRole.WORKER,
        db_index=True,
    )

    # Profile
    name = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to="avatars/%Y/%m/", null=True, blank=True)
    bio = models.TextField(max_length=500, blank=True)

    # Rating (0.00 – 5.00)
    rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("5"))],
    )
    rating_count = models.PositiveIntegerField(default=0)

    # Account status
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False, db_index=True)
    block_reason = models.TextField(blank=True)

    # Profile completeness
    is_profile_complete = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "phone_number"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "accounts_users"
        verbose_name = "User"
        verbose_name_plural = "Users"
        indexes = [
            models.Index(fields=["phone_number"]),
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.phone_number} ({self.role})"

    @property
    def is_employer(self) -> bool:
        return self.role == UserRole.EMPLOYER

    @property
    def is_worker(self) -> bool:
        return self.role == UserRole.WORKER

    @property
    def display_name(self) -> str:
        return self.name or str(self.phone_number)

    def update_rating(self, new_rating: Decimal) -> None:
        """Recalculate average rating after a new review."""
        total = self.rating * self.rating_count + new_rating
        self.rating_count += 1
        self.rating = total / self.rating_count
        self.save(update_fields=["rating", "rating_count"])


class OTPCode(models.Model):
    """
    One-Time Password storage.

    Stored in Redis for performance, but DB record kept for audit trail.
    Automatically expires based on OTP_EXPIRY_SECONDS setting.
    """

    phone_number = PhoneNumberField(db_index=True)
    code = models.CharField(max_length=10)
    is_used = models.BooleanField(default=False, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "accounts_otp_codes"
        verbose_name = "OTP Code"
        verbose_name_plural = "OTP Codes"
        indexes = [
            models.Index(fields=["phone_number", "is_used"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"OTP for {self.phone_number} (used={self.is_used})"

    @property
    def is_expired(self) -> bool:
        from django.utils import timezone
        return timezone.now() > self.expires_at


class TelegramOTP(models.Model):
    """
    Stores the request_id returned by Telegram Gateway after sending an OTP.
    Used to verify the code via checkVerificationStatus.
    """

    phone_number = PhoneNumberField(db_index=True)
    request_id = models.CharField(max_length=255, unique=True, db_index=True)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "accounts_telegram_otps"
        verbose_name = "Telegram OTP"
        verbose_name_plural = "Telegram OTPs"

    def __str__(self) -> str:
        return f"TelegramOTP for {self.phone_number} (used={self.is_used})"

    def is_expired(self) -> bool:
        from django.utils import timezone
        return (timezone.now() - self.created_at).total_seconds() > 300


class DeviceToken(models.Model):
    """
    Push notification device tokens (Firebase FCM).
    One user can have multiple devices.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="device_tokens",
    )
    token = models.TextField(unique=True, db_index=True)
    platform = models.CharField(
        max_length=10,
        choices=[("ios", "iOS"), ("android", "Android"), ("web", "Web")],
        default="android",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "accounts_device_tokens"
        verbose_name = "Device Token"
        verbose_name_plural = "Device Tokens"
        indexes = [
            models.Index(fields=["user", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.user.phone_number} — {self.platform}"
