"""
Tests for the payments / wallet module.
Covers: deposit initiation, wallet balance, transaction history, commission.
"""

from unittest.mock import patch

import pytest

from apps.core.utils import calculate_commission
from apps.payments.models import Transaction, TransactionType, Wallet
from apps.payments.services import DepositService, WalletService


@pytest.mark.django_db
class TestWalletView:
    """GET /api/v1/wallet/"""

    URL = "/api/v1/wallet/"

    def test_get_wallet_returns_balance(self, employer_client, employer_user):
        resp = employer_client.get(self.URL)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "balance" in data
        assert "balance_uzs" in data
        assert data["balance"] == 10_000_000

    def test_unauthenticated_cannot_view_wallet(self, api_client):
        resp = api_client.get(self.URL)
        assert resp.status_code == 401


@pytest.mark.django_db
class TestDepositView:
    """POST /api/v1/wallet/deposit/"""

    URL = "/api/v1/wallet/deposit/"

    def test_initiate_deposit_returns_payment_url(self, employer_client):
        resp = employer_client.post(self.URL, {"amount": 500_000, "provider": "mock"})
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "payment_url" in data
        assert "request_id" in data

    def test_deposit_below_minimum_fails(self, employer_client):
        resp = employer_client.post(self.URL, {"amount": 50, "provider": "mock"})
        assert resp.status_code in (400, 422)

    def test_deposit_creates_payment_request(self, employer_client, employer_user):
        from apps.payments.models import PaymentRequest
        resp = employer_client.post(self.URL, {"amount": 200_000, "provider": "mock"})
        assert resp.status_code == 201
        assert PaymentRequest.objects.filter(wallet__user=employer_user).exists()


@pytest.mark.django_db
class TestTransactionListView:
    """GET /api/v1/wallet/transactions/"""

    URL = "/api/v1/wallet/transactions/"

    def test_returns_transaction_history(self, employer_client, employer_user, open_job):
        # open_job fixture creates an escrow transaction
        resp = employer_client.get(self.URL)
        assert resp.status_code == 200
        assert resp.json()["data"]["count"] >= 1

    def test_pagination_works(self, employer_client):
        resp = employer_client.get(self.URL, {"page": 1, "page_size": 5})
        assert resp.status_code == 200


@pytest.mark.django_db
class TestWalletService:
    """Unit tests for WalletService."""

    def test_deposit_credits_balance(self, employer_user):
        wallet = Wallet.objects.get(user=employer_user)
        original = wallet.balance

        WalletService.deposit(wallet, amount=50_000, provider="mock")

        wallet.refresh_from_db()
        assert wallet.balance == original + 50_000

    def test_deposit_creates_transaction(self, employer_user):
        wallet = Wallet.objects.get(user=employer_user)
        tx = WalletService.deposit(wallet, amount=100_000, provider="mock")

        assert tx.transaction_type == TransactionType.DEPOSIT
        assert tx.direction == "credit"
        assert tx.amount == 100_000
        assert tx.balance_after == tx.balance_before + 100_000

    def test_deduct_for_job_moves_to_held(self, employer_user, open_job):
        wallet = Wallet.objects.get(user=employer_user)
        # Balance was already deducted by the fixture; verify held
        assert wallet.held_balance == open_job.price

    def test_release_payment_credits_worker(self, employer_user, worker_user, accepted_job):
        accepted_job.status = "in_progress"
        accepted_job.save()

        # Fund employer escrow
        employer_wallet = Wallet.objects.get(user=employer_user)
        employer_wallet.held_balance = accepted_job.price
        employer_wallet.save()

        worker_wallet = Wallet.objects.get(user=worker_user)
        before = worker_wallet.balance

        WalletService.release_job_payment(accepted_job)

        worker_wallet.refresh_from_db()
        _, worker_cut = calculate_commission(accepted_job.price)
        assert worker_wallet.balance == before + worker_cut

    def test_refund_returns_to_employer(self, employer_user, open_job):
        wallet = Wallet.objects.get(user=employer_user)
        balance_before = wallet.balance
        held_before = wallet.held_balance

        open_job.status = "cancelled"
        open_job.save()

        WalletService.refund_job(open_job)

        wallet.refresh_from_db()
        assert wallet.balance == balance_before + open_job.price
        assert wallet.held_balance == held_before - open_job.price


@pytest.mark.django_db
class TestCommissionCalculation:
    """Test the commission calculation utility."""

    def test_10_percent_commission(self):
        commission, worker = calculate_commission(100_000)
        assert commission == 10_000
        assert worker == 90_000

    def test_custom_percent(self):
        commission, worker = calculate_commission(200_000, percent=15)
        assert commission == 30_000
        assert worker == 170_000

    def test_zero_commission(self):
        commission, worker = calculate_commission(100_000, percent=0)
        assert commission == 0
        assert worker == 100_000
