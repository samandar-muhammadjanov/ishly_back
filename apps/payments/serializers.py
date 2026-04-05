"""Payments serializers."""

from rest_framework import serializers

from .models import Transaction, TransactionType, Wallet


class WalletSerializer(serializers.ModelSerializer):
    balance_uzs = serializers.FloatField(read_only=True)
    held_balance_uzs = serializers.FloatField(read_only=True)

    class Meta:
        model = Wallet
        fields = [
            "id", "balance", "balance_uzs",
            "held_balance", "held_balance_uzs",
            "total_earned", "total_spent",
            "updated_at",
        ]
        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):
    amount_uzs = serializers.FloatField(read_only=True)
    job_title = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            "id", "transaction_type", "direction",
            "amount", "amount_uzs",
            "balance_before", "balance_after",
            "status", "description",
            "provider", "external_id",
            "job", "job_title",
            "created_at",
        ]
        read_only_fields = fields

    def get_job_title(self, obj: Transaction) -> str | None:
        if obj.job_id:
            return obj.job.title if obj.job else None
        return None


class InitiateDepositSerializer(serializers.Serializer):
    amount = serializers.IntegerField(
        min_value=100,
        help_text="Deposit amount in tiyin (100 tiyin = 1 UZS)",
    )
    provider = serializers.ChoiceField(
        choices=["payme", "click", "mock"],
        default="mock",
    )


class DepositResponseSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    payment_url = serializers.URLField()
    amount = serializers.IntegerField()
    provider = serializers.CharField()
