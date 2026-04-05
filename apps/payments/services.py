"""
Payments service layer.
Handles all wallet operations: deposits, escrow, payouts, refunds.
All money movements are wrapped in DB transactions with row locking.
"""

import logging
from typing import Any

from django.conf import settings
from django.db import transaction

from apps.core.exceptions import (
    InsufficientBalanceException,
    ValidationException,
)
from apps.core.utils import calculate_commission

from .models import PaymentRequest, Transaction, TransactionStatus, TransactionType, Wallet

logger = logging.getLogger(__name__)

MIN_DEPOSIT = getattr(settings, "MIN_DEPOSIT_AMOUNT", 10000)
MAX_DEPOSIT = getattr(settings, "MAX_DEPOSIT_AMOUNT", 10_000_000)


class WalletService:
    """
    Core wallet operations.
    Every balance change must go through this service to maintain
    a consistent transaction ledger.
    """

    @classmethod
    @transaction.atomic
    def deposit(cls, wallet: Wallet, amount: int, provider: str = "mock", external_id: str = "", meta: dict | None = None) -> Transaction:
        """
        Credit funds to a wallet (e.g., after Payme/Click payment confirmed).

        Args:
            wallet: Locked wallet instance (caller should use select_for_update)
            amount: Amount in tiyin
            provider: Payment provider name
            external_id: Provider's transaction ID
            meta: Additional provider metadata
        """
        if amount < MIN_DEPOSIT:
            raise ValidationException(f"Minimum deposit is {MIN_DEPOSIT} tiyin.")
        if amount > MAX_DEPOSIT:
            raise ValidationException(f"Maximum deposit is {MAX_DEPOSIT} tiyin.")

        balance_before = wallet.balance
        wallet.balance += amount
        wallet.save(update_fields=["balance", "updated_at"])

        tx = Transaction.objects.create(
            wallet=wallet,
            transaction_type=TransactionType.DEPOSIT,
            direction="credit",
            amount=amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            status=TransactionStatus.COMPLETED,
            provider=provider,
            external_id=external_id,
            description=f"Deposit via {provider}",
            meta=meta or {},
        )

        logger.info(
            "Deposit: wallet=%s, amount=%s, balance=%s→%s",
            wallet.user_id, amount, balance_before, wallet.balance,
        )
        return tx

    @classmethod
    @transaction.atomic
    def deduct_for_job(cls, wallet: Wallet, job) -> Transaction:
        """
        Deduct job price from employer wallet and hold in escrow.
        Called immediately when a job is created.
        """
        amount = job.price
        if wallet.balance < amount:
            raise InsufficientBalanceException(
                f"Insufficient balance. Need {amount}, have {wallet.balance}."
            )

        balance_before = wallet.balance
        wallet.balance -= amount
        wallet.held_balance += amount
        wallet.total_spent += amount
        wallet.save(update_fields=["balance", "held_balance", "total_spent", "updated_at"])

        tx = Transaction.objects.create(
            wallet=wallet,
            transaction_type=TransactionType.JOB_PAYMENT,
            direction="debit",
            amount=amount,
            balance_before=balance_before,
            balance_after=wallet.balance,
            status=TransactionStatus.COMPLETED,
            job=job,
            provider="internal",
            description=f"Escrow for job: {job.title}",
        )

        logger.info("Escrow deducted: job=%s, amount=%s", job.id, amount)
        return tx

    @classmethod
    @transaction.atomic
    def release_job_payment(cls, job) -> tuple[Transaction, Transaction]:
        """
        Release escrowed funds after job completion.

        - Platform commission (10%) kept in employer's held_balance
        - 90% credited to worker wallet

        Returns: (commission_tx, worker_tx)
        """
        from apps.accounts.models import User

        commission_amount, worker_amount = calculate_commission(job.price)

        # Lock both wallets
        employer_wallet = (
            Wallet.objects
            .select_for_update()
            .get(user=job.employer)
        )
        worker_wallet = (
            Wallet.objects
            .select_for_update()
            .get(user=job.worker)
        )

        # Release held funds from employer wallet
        employer_wallet.held_balance -= job.price
        employer_wallet.save(update_fields=["held_balance", "updated_at"])

        # Commission transaction (debit from employer held)
        commission_tx = Transaction.objects.create(
            wallet=employer_wallet,
            transaction_type=TransactionType.COMMISSION,
            direction="debit",
            amount=commission_amount,
            balance_before=employer_wallet.balance,
            balance_after=employer_wallet.balance,
            status=TransactionStatus.COMPLETED,
            job=job,
            provider="internal",
            description=f"Platform commission ({settings.PLATFORM_COMMISSION_PERCENT}%) for job: {job.title}",
        )

        # Payout to worker
        worker_balance_before = worker_wallet.balance
        worker_wallet.balance += worker_amount
        worker_wallet.total_earned += worker_amount
        worker_wallet.save(update_fields=["balance", "total_earned", "updated_at"])

        worker_tx = Transaction.objects.create(
            wallet=worker_wallet,
            transaction_type=TransactionType.JOB_RELEASE,
            direction="credit",
            amount=worker_amount,
            balance_before=worker_balance_before,
            balance_after=worker_wallet.balance,
            status=TransactionStatus.COMPLETED,
            job=job,
            provider="internal",
            description=f"Payout for job: {job.title}",
        )

        logger.info(
            "Payment released: job=%s, commission=%s, worker_payout=%s",
            job.id, commission_amount, worker_amount,
        )
        return commission_tx, worker_tx

    @classmethod
    @transaction.atomic
    def refund_job(cls, job) -> Transaction:
        """
        Refund employer when a job is cancelled.
        Releases the held escrow amount back to employer's available balance.
        """
        employer_wallet = (
            Wallet.objects
            .select_for_update()
            .get(user=job.employer)
        )

        # Return escrowed amount to employer
        held = min(job.price, employer_wallet.held_balance)
        balance_before = employer_wallet.balance
        employer_wallet.balance += held
        employer_wallet.held_balance -= held
        employer_wallet.total_spent = max(0, employer_wallet.total_spent - held)
        employer_wallet.save(update_fields=["balance", "held_balance", "total_spent", "updated_at"])

        tx = Transaction.objects.create(
            wallet=employer_wallet,
            transaction_type=TransactionType.REFUND,
            direction="credit",
            amount=held,
            balance_before=balance_before,
            balance_after=employer_wallet.balance,
            status=TransactionStatus.COMPLETED,
            job=job,
            provider="internal",
            description=f"Refund for cancelled job: {job.title}",
        )

        logger.info("Refund issued: job=%s, amount=%s", job.id, held)
        return tx

    @classmethod
    def get_balance(cls, user) -> dict[str, Any]:
        """Get wallet summary for a user."""
        try:
            wallet = Wallet.objects.get(user=user)
            return {
                "balance": wallet.balance,
                "balance_uzs": wallet.balance_uzs,
                "held_balance": wallet.held_balance,
                "held_balance_uzs": wallet.held_balance_uzs,
                "total_earned": wallet.total_earned,
                "total_spent": wallet.total_spent,
            }
        except Wallet.DoesNotExist:
            return {"balance": 0, "balance_uzs": 0, "held_balance": 0}


class DepositService:
    """
    Manages deposit requests via external payment providers.
    """

    @classmethod
    @transaction.atomic
    def initiate_deposit(cls, user, amount: int, provider_name: str) -> dict[str, Any]:
        """
        Create a PaymentRequest and get a payment URL from the provider.

        Args:
            user: The user depositing funds
            amount: Amount in tiyin
            provider_name: "payme" or "click"

        Returns:
            dict with payment_url and request_id
        """
        if amount < MIN_DEPOSIT:
            raise ValidationException(f"Minimum deposit is {MIN_DEPOSIT} tiyin.")
        if amount > MAX_DEPOSIT:
            raise ValidationException(f"Maximum deposit is {MAX_DEPOSIT} tiyin.")

        wallet = Wallet.objects.get(user=user)

        # Create pending request
        payment_request = PaymentRequest.objects.create(
            wallet=wallet,
            provider=provider_name,
            amount=amount,
        )

        # Get payment URL from provider
        from .providers.payment_providers import get_payment_provider
        provider = get_payment_provider(provider_name)
        result = provider.create_payment(
            amount=amount,
            order_id=str(payment_request.id),
            description=f"Deposit to GIG Marketplace wallet",
        )

        payment_request.external_id = result["external_id"]
        payment_request.payment_url = result["payment_url"]
        payment_request.save(update_fields=["external_id", "payment_url", "updated_at"])

        logger.info(
            "Deposit initiated: user=%s, amount=%s, provider=%s, request=%s",
            user.id, amount, provider_name, payment_request.id,
        )

        return {
            "request_id": str(payment_request.id),
            "payment_url": result["payment_url"],
            "amount": amount,
            "provider": provider_name,
        }

    @classmethod
    @transaction.atomic
    def confirm_deposit(cls, payment_request_id: str, external_id: str = "") -> Transaction:
        """
        Called by payment provider webhook to confirm a successful deposit.
        Credits funds to the user's wallet.
        """
        try:
            payment_request = (
                PaymentRequest.objects
                .select_for_update()
                .select_related("wallet")
                .get(id=payment_request_id, status=TransactionStatus.PENDING)
            )
        except PaymentRequest.DoesNotExist:
            raise ValidationException("Payment request not found or already processed.")

        # Lock wallet before crediting
        wallet = (
            Wallet.objects
            .select_for_update()
            .get(id=payment_request.wallet_id)
        )

        tx = WalletService.deposit(
            wallet=wallet,
            amount=payment_request.amount,
            provider=payment_request.provider,
            external_id=external_id or payment_request.external_id,
        )

        payment_request.status = TransactionStatus.COMPLETED
        payment_request.save(update_fields=["status", "updated_at"])

        logger.info(
            "Deposit confirmed: request=%s, amount=%s",
            payment_request_id, payment_request.amount,
        )
        return tx
