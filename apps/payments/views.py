"""Payments views."""

import logging

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsPagination
from apps.core.permissions import IsActiveUser

from .models import Transaction, Wallet
from .serializers import (
    DepositResponseSerializer,
    InitiateDepositSerializer,
    TransactionSerializer,
    WalletSerializer,
)
from .services import DepositService, WalletService

logger = logging.getLogger(__name__)


class WalletView(APIView):
    """GET /wallet/ — get current user's wallet balance."""

    permission_classes = [IsAuthenticated, IsActiveUser]

    @extend_schema(tags=["Payments"], summary="Get wallet balance")
    def get(self, request: Request) -> Response:
        try:
            wallet = Wallet.objects.get(user=request.user)
        except Wallet.DoesNotExist:
            # Auto-create if missing (shouldn't happen due to signal)
            wallet = Wallet.objects.create(user=request.user)

        return Response(WalletSerializer(wallet).data)


class TransactionListView(APIView):
    """GET /wallet/transactions/ — paginated transaction history."""

    permission_classes = [IsAuthenticated, IsActiveUser]
    pagination_class = StandardResultsPagination

    @extend_schema(tags=["Payments"], summary="List transaction history")
    def get(self, request: Request) -> Response:
        qs = (
            Transaction.objects
            .filter(wallet__user=request.user)
            .select_related("job")
            .order_by("-created_at")
        )

        # Filter by type
        tx_type = request.query_params.get("type")
        if tx_type and tx_type in [t.value for t in Transaction.transaction_type.field.choices]:
            qs = qs.filter(transaction_type=tx_type)

        paginator = StandardResultsPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = TransactionSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class InitiateDepositView(APIView):
    """POST /wallet/deposit/ — initiate a deposit via payment provider."""

    permission_classes = [IsAuthenticated, IsActiveUser]

    @extend_schema(
        tags=["Payments"],
        summary="Initiate wallet deposit",
        request=InitiateDepositSerializer,
        responses={201: DepositResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = InitiateDepositSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = DepositService.initiate_deposit(
            user=request.user,
            amount=serializer.validated_data["amount"],
            provider_name=serializer.validated_data["provider"],
        )

        return Response(result, status=status.HTTP_201_CREATED)


class PaymeWebhookView(APIView):
    """POST /payments/webhook/payme/ — Payme payment callback."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        from .providers.payment_providers import get_payment_provider

        provider = get_payment_provider("payme")
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")

        if not provider.verify_webhook(request.data, auth_header):
            return Response(
                {"error": {"code": -32504, "message": "Insufficient privilege to perform this method"}},
                status=200,
            )

        method = request.data.get("method", "")
        params = request.data.get("params", {})
        request_id = request.data.get("id", 0)

        try:
            result = self._handle_payme_method(method, params)
            return Response({"id": request_id, "result": result})
        except Exception as e:
            logger.error("Payme webhook error: %s", e, exc_info=True)
            return Response(
                {"id": request_id, "error": {"code": -31008, "message": str(e)}},
                status=200,
            )

    def _handle_payme_method(self, method: str, params: dict) -> dict:
        if method == "PerformTransaction":
            order_id = params.get("account", {}).get("order_id")
            if order_id:
                DepositService.confirm_deposit(order_id)
            return {"transaction": params.get("id"), "perform_time": 0, "state": 2}
        return {}


class ClickWebhookView(APIView):
    """POST /payments/webhook/click/ — Click payment callback."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(exclude=True)
    def post(self, request: Request) -> Response:
        from .providers.payment_providers import get_payment_provider

        provider = get_payment_provider("click")
        sign = request.data.get("sign_string", "")

        if not provider.verify_webhook(request.data, sign):
            return Response({"error": -1, "error_note": "Invalid signature"})

        action = request.data.get("action")
        order_id = request.data.get("merchant_trans_id")

        if action == 1 and order_id:  # Confirm
            try:
                DepositService.confirm_deposit(order_id)
            except Exception as e:
                logger.error("Click confirm error: %s", e)
                return Response({"error": -9, "error_note": str(e)})

        return Response({"error": 0, "error_note": "Success"})
