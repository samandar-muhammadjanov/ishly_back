"""Payments admin configuration."""

from django.contrib import admin
from django.utils.html import format_html

from .models import PaymentRequest, Transaction, TransactionType, Wallet


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ["user", "balance_display", "held_display", "total_earned_display", "updated_at"]
    search_fields = ["user__phone_number"]
    readonly_fields = ["id", "created_at", "updated_at"]

    def balance_display(self, obj):
        return f"{obj.balance_uzs:,.2f} UZS"
    balance_display.short_description = "Balance"

    def held_display(self, obj):
        return f"{obj.held_balance_uzs:,.2f} UZS"
    held_display.short_description = "Held"

    def total_earned_display(self, obj):
        return f"{obj.total_earned / 100:,.2f} UZS"
    total_earned_display.short_description = "Total Earned"


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        "id_short", "wallet_user", "type_badge",
        "amount_display", "direction", "status", "created_at"
    ]
    list_filter = ["transaction_type", "direction", "status", "created_at"]
    search_fields = ["wallet__user__phone_number", "external_id"]
    readonly_fields = [f.name for f in Transaction._meta.get_fields() if hasattr(f, "name")]
    ordering = ["-created_at"]

    def id_short(self, obj):
        return str(obj.id)[:8] + "..."
    id_short.short_description = "ID"

    def wallet_user(self, obj):
        return obj.wallet.user.phone_number
    wallet_user.short_description = "User"

    def amount_display(self, obj):
        sign = "+" if obj.direction == "credit" else "-"
        color = "#28a745" if obj.direction == "credit" else "#dc3545"
        return format_html(
            '<span style="color:{}">{}{:,.0f} UZS</span>',
            color, sign, obj.amount_uzs
        )
    amount_display.short_description = "Amount"

    def type_badge(self, obj):
        colors = {
            TransactionType.DEPOSIT: "#28a745",
            TransactionType.JOB_PAYMENT: "#ffc107",
            TransactionType.JOB_RELEASE: "#17a2b8",
            TransactionType.COMMISSION: "#6f42c1",
            TransactionType.REFUND: "#fd7e14",
        }
        color = colors.get(obj.transaction_type, "#6c757d")
        return format_html(
            '<span style="background:{};color:white;padding:2px 6px;border-radius:3px;font-size:11px">{}</span>',
            color, obj.get_transaction_type_display()
        )
    type_badge.short_description = "Type"

    def has_add_permission(self, request):
        return False  # Transactions are created programmatically only

    def has_change_permission(self, request, obj=None):
        return False  # Immutable ledger


@admin.register(PaymentRequest)
class PaymentRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "wallet_user", "provider", "amount_display", "status", "created_at"]
    list_filter = ["provider", "status", "created_at"]
    search_fields = ["wallet__user__phone_number", "external_id"]
    readonly_fields = ["id", "created_at", "updated_at"]

    def wallet_user(self, obj):
        return obj.wallet.user.phone_number
    wallet_user.short_description = "User"

    def amount_display(self, obj):
        return f"{obj.amount / 100:,.2f} UZS"
    amount_display.short_description = "Amount"
