"""
Payments models.
Internal wallet system with full transaction ledger.
"""

import uuid

from django.core.validators import MinValueValidator
from django.db import models

from apps.accounts.models import User


class TransactionType(models.TextChoices):
    DEPOSIT = "deposit", "Deposit"
    JOB_PAYMENT = "job_payment", "Job Payment (Escrow)"
    JOB_RELEASE = "job_release", "Job Release (Worker Payout)"
    COMMISSION = "commission", "Platform Commission"
    REFUND = "refund", "Refund"
    WITHDRAWAL = "withdrawal", "Withdrawal"


class TransactionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    REVERSED = "reversed", "Reversed"


class Wallet(models.Model):
    """
    User wallet.

    - balance: current available balance (in tiyin, 1 UZS = 100 tiyin)
    - held_balance: funds locked in escrow for active jobs
    - total_earned: lifetime earnings (workers only)
    - total_spent: lifetime spent (employers only)

    balance is stored as an integer to avoid floating-point errors.
    All financial operations must use select_for_update() to prevent
    race conditions.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="wallet",
    )
    balance = models.PositiveBigIntegerField(
        default=0,
        help_text="Available balance in tiyin",
    )
    held_balance = models.PositiveBigIntegerField(
        default=0,
        help_text="Funds held in escrow for active jobs",
    )
    total_earned = models.PositiveBigIntegerField(
        default=0,
        help_text="Lifetime earned (workers only)",
    )
    total_spent = models.PositiveBigIntegerField(
        default=0,
        help_text="Lifetime spent (employers only)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments_wallets"
        verbose_name = "Wallet"
        verbose_name_plural = "Wallets"

    def __str__(self) -> str:
        return f"Wallet({self.user.phone_number}) — {self.balance} tiyin"

    @property
    def balance_uzs(self) -> float:
        return self.balance / 100

    @property
    def held_balance_uzs(self) -> float:
        return self.held_balance / 100


class Transaction(models.Model):
    """
    Immutable financial transaction record.

    Every money movement must create a Transaction.
    Transactions are never updated or deleted — only new ones added.
    This ensures a complete, auditable financial ledger.

    direction:
      - credit: money coming IN  (+)
      - debit:  money going OUT  (-)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
        db_index=True,
    )
    direction = models.CharField(
        max_length=6,
        choices=[("credit", "Credit"), ("debit", "Debit")],
    )
    amount = models.PositiveBigIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Amount in tiyin",
    )
    balance_before = models.PositiveBigIntegerField(
        help_text="Wallet balance before this transaction",
    )
    balance_after = models.PositiveBigIntegerField(
        help_text="Wallet balance after this transaction",
    )
    status = models.CharField(
        max_length=10,
        choices=TransactionStatus.choices,
        default=TransactionStatus.COMPLETED,
        db_index=True,
    )

    # References
    job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    external_id = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
        help_text="ID from external payment provider (Payme, Click)",
    )
    provider = models.CharField(
        max_length=50,
        blank=True,
        help_text="Payment provider name (payme, click, internal)",
    )
    description = models.CharField(max_length=500, blank=True)
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "payments_transactions"
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["wallet", "created_at"]),
            models.Index(fields=["wallet", "transaction_type"]),
            models.Index(fields=["job"]),
            models.Index(fields=["external_id"]),
        ]

    def __str__(self) -> str:
        sign = "+" if self.direction == "credit" else "-"
        return (
            f"{self.transaction_type} {sign}{self.amount} tiyin "
            f"[{self.wallet.user.phone_number}]"
        )

    @property
    def amount_uzs(self) -> float:
        return self.amount / 100


class PaymentRequest(models.Model):
    """
    Tracks deposit requests initiated via Payme / Click.
    Updated by payment provider webhook callbacks.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.PROTECT,
        related_name="payment_requests",
    )
    provider = models.CharField(
        max_length=20,
        choices=[("payme", "Payme"), ("click", "Click")],
    )
    amount = models.PositiveBigIntegerField()
    status = models.CharField(
        max_length=20,
        choices=TransactionStatus.choices,
        default=TransactionStatus.PENDING,
        db_index=True,
    )
    external_id = models.CharField(max_length=200, blank=True, db_index=True)
    payment_url = models.URLField(blank=True)
    meta = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "payments_payment_requests"
        verbose_name = "Payment Request"
        verbose_name_plural = "Payment Requests"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.provider} — {self.amount} tiyin — {self.status}"
