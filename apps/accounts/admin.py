"""Admin configuration for accounts app."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html

from .models import DeviceToken, OTPCode, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for the User model."""

    list_display = [
        "phone_number", "name", "role", "rating", "balance_display",
        "is_active", "is_blocked", "created_at",
    ]
    list_filter = ["role", "is_active", "is_blocked", "is_staff", "created_at"]
    search_fields = ["phone_number", "name"]
    ordering = ["-created_at"]
    readonly_fields = ["id", "created_at", "updated_at", "last_seen", "rating", "rating_count"]

    fieldsets = (
        ("Identity", {"fields": ("id", "phone_number", "password")}),
        ("Profile", {"fields": ("name", "avatar", "bio", "role")}),
        ("Stats", {"fields": ("rating", "rating_count")}),
        ("Status", {"fields": ("is_active", "is_blocked", "block_reason", "is_staff", "is_superuser")}),
        ("Timestamps", {"fields": ("created_at", "updated_at", "last_seen")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("phone_number", "role", "password1", "password2"),
        }),
    )

    # Remove email-based fields from BaseUserAdmin
    filter_horizontal = ["groups", "user_permissions"]

    def balance_display(self, obj: User) -> str:
        try:
            balance = obj.wallet.balance
            return f"{balance:,} UZS"
        except Exception:
            return "—"
    balance_display.short_description = "Balance"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("wallet")

    actions = ["block_users", "unblock_users"]

    @admin.action(description="Block selected users")
    def block_users(self, request, queryset):
        from .services import UserService
        for user in queryset:
            UserService.block_user(user, reason="Blocked by admin")
        self.message_user(request, f"{queryset.count()} users blocked.")

    @admin.action(description="Unblock selected users")
    def unblock_users(self, request, queryset):
        from .services import UserService
        for user in queryset:
            UserService.unblock_user(user)
        self.message_user(request, f"{queryset.count()} users unblocked.")


@admin.register(OTPCode)
class OTPCodeAdmin(admin.ModelAdmin):
    list_display = ["phone_number", "is_used", "attempts", "expires_at", "created_at"]
    list_filter = ["is_used", "created_at"]
    search_fields = ["phone_number"]
    readonly_fields = ["id", "created_at", "used_at"]
    ordering = ["-created_at"]


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "platform", "is_active", "created_at", "last_used_at"]
    list_filter = ["platform", "is_active"]
    search_fields = ["user__phone_number", "token"]
    readonly_fields = ["id", "created_at"]
