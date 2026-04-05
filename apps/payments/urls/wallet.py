"""Wallet URL patterns."""

from django.urls import path

from apps.payments.views import InitiateDepositView, TransactionListView, WalletView

app_name = "wallet"

urlpatterns = [
    path("", WalletView.as_view(), name="wallet_detail"),
    path("deposit/", InitiateDepositView.as_view(), name="initiate_deposit"),
    path("transactions/", TransactionListView.as_view(), name="transaction_list"),
]
