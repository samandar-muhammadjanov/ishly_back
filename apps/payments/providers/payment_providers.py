"""
Payment provider abstraction layer.
Defines a common interface; concrete providers implement it.
Easily swap providers without touching business logic.
"""

import logging
import uuid
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ----------------------------
# Abstract Base Provider
# ----------------------------

class BasePaymentProvider(ABC):
    """
    All payment providers must implement this interface.
    Methods return a standardised dict so the service layer
    never needs to know which provider it is talking to.
    """

    @abstractmethod
    def create_payment(
        self,
        amount: int,
        order_id: str,
        description: str,
        return_url: str = "",
    ) -> dict[str, Any]:
        """
        Initiate a payment with the provider.

        Returns:
            {
                "external_id": str,
                "payment_url": str,
                "status": "pending",
            }
        """
        ...

    @abstractmethod
    def check_payment(self, external_id: str) -> dict[str, Any]:
        """
        Query the current status of a payment.

        Returns:
            {
                "external_id": str,
                "status": "pending" | "completed" | "failed",
                "amount": int,
            }
        """
        ...

    @abstractmethod
    def verify_webhook(self, payload: dict[str, Any], signature: str) -> bool:
        """Verify an incoming webhook is genuinely from the provider."""
        ...


# ----------------------------
# Mock Provider (Development / Testing)
# ----------------------------

class MockPaymentProvider(BasePaymentProvider):
    """
    Mock provider that always succeeds.
    Used in development and test environments.
    In production, swap for PaymeProvider or ClickProvider.
    """

    def create_payment(
        self,
        amount: int,
        order_id: str,
        description: str,
        return_url: str = "",
    ) -> dict[str, Any]:
        external_id = f"mock_{uuid.uuid4().hex[:12]}"
        logger.info(
            "[MockPayment] create_payment: amount=%s, order_id=%s, ext_id=%s",
            amount, order_id, external_id,
        )
        return {
            "external_id": external_id,
            "payment_url": f"https://mock-payment.example.com/pay/{external_id}",
            "status": "pending",
        }

    def check_payment(self, external_id: str) -> dict[str, Any]:
        logger.info("[MockPayment] check_payment: %s", external_id)
        return {
            "external_id": external_id,
            "status": "completed",
            "amount": 0,
        }

    def verify_webhook(self, payload: dict[str, Any], signature: str) -> bool:
        return True


# ----------------------------
# Payme Provider (Uzbekistan)
# ----------------------------

class PaymeProvider(BasePaymentProvider):
    """
    Payme payment gateway integration (Uzbekistan).
    Docs: https://developer.help.paycom.uz/

    Uses JSON-RPC 2.0 protocol.
    """

    BASE_URL = "https://checkout.paycom.uz/api"
    TEST_URL = "https://test.paycom.uz/api"

    def __init__(self, merchant_id: str, key: str, test_mode: bool = True):
        self.merchant_id = merchant_id
        self.key = key
        self.base_url = self.TEST_URL if test_mode else self.BASE_URL
        self._session = None

    def _get_auth_header(self) -> str:
        import base64
        credentials = f"{self.merchant_id}:{self.key}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"

    def _call(self, method: str, params: dict) -> dict[str, Any]:
        """Make a JSON-RPC call to Payme API."""
        import requests
        payload = {
            "id": str(uuid.uuid4()),
            "method": method,
            "params": params,
        }
        try:
            resp = requests.post(
                self.base_url,
                json=payload,
                headers={
                    "X-Auth": self._get_auth_header(),
                    "Content-Type": "application/json",
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error("Payme API call failed: %s", e)
            raise

    def create_payment(
        self,
        amount: int,
        order_id: str,
        description: str,
        return_url: str = "",
    ) -> dict[str, Any]:
        # Payme expects amount in tiyin
        checkout_url = (
            f"https://{'test.' if True else ''}paycom.uz/{self.merchant_id}"
            f"?amount={amount}&order_id={order_id}&description={description}"
        )
        logger.info("[Payme] create_payment: order_id=%s, amount=%s", order_id, amount)
        return {
            "external_id": order_id,
            "payment_url": checkout_url,
            "status": "pending",
        }

    def check_payment(self, external_id: str) -> dict[str, Any]:
        result = self._call("CheckTransaction", {"id": external_id})
        state = result.get("result", {}).get("state", 0)
        status_map = {2: "completed", -1: "failed", -2: "failed"}
        return {
            "external_id": external_id,
            "status": status_map.get(state, "pending"),
            "amount": result.get("result", {}).get("amount", 0),
        }

    def verify_webhook(self, payload: dict[str, Any], signature: str) -> bool:
        import base64
        try:
            decoded = base64.b64decode(signature).decode()
            merchant_id, key = decoded.split(":")
            return merchant_id == self.merchant_id and key == self.key
        except Exception:
            return False


# ----------------------------
# Click Provider (Uzbekistan)
# ----------------------------

class ClickProvider(BasePaymentProvider):
    """
    Click payment gateway integration (Uzbekistan).
    Docs: https://docs.click.uz/
    """

    BASE_URL = "https://api.click.uz/v2/merchant"

    def __init__(self, service_id: str, merchant_id: str, secret_key: str):
        self.service_id = service_id
        self.merchant_id = merchant_id
        self.secret_key = secret_key

    def _get_auth_header(self) -> dict[str, str]:
        import hashlib
        import time
        timestamp = str(int(time.time()))
        digest = hashlib.sha1(
            f"{timestamp}{self.secret_key}".encode()
        ).hexdigest()
        return {
            "Auth": f"{self.merchant_id}:{digest}:{timestamp}",
            "Content-Type": "application/json",
        }

    def create_payment(
        self,
        amount: int,
        order_id: str,
        description: str,
        return_url: str = "",
    ) -> dict[str, Any]:
        # Amount for Click must be in UZS (not tiyin)
        amount_uzs = amount / 100
        payment_url = (
            f"https://my.click.uz/services/pay"
            f"?service_id={self.service_id}"
            f"&merchant_id={self.merchant_id}"
            f"&amount={amount_uzs}"
            f"&transaction_param={order_id}"
            f"&return_url={return_url}"
        )
        logger.info("[Click] create_payment: order_id=%s, amount=%s", order_id, amount)
        return {
            "external_id": order_id,
            "payment_url": payment_url,
            "status": "pending",
        }

    def check_payment(self, external_id: str) -> dict[str, Any]:
        import requests
        try:
            resp = requests.get(
                f"{self.BASE_URL}/check_payment/{self.service_id}/{external_id}/",
                headers=self._get_auth_header(),
                timeout=15,
            )
            data = resp.json()
            status = "completed" if data.get("error") == 0 else "pending"
            return {
                "external_id": external_id,
                "status": status,
                "amount": data.get("amount", 0),
            }
        except Exception as e:
            logger.error("Click check_payment failed: %s", e)
            return {"external_id": external_id, "status": "pending", "amount": 0}

    def verify_webhook(self, payload: dict[str, Any], signature: str) -> bool:
        import hashlib
        sign_string = (
            f"{payload.get('click_trans_id')}"
            f"{self.service_id}"
            f"{self.secret_key}"
            f"{payload.get('merchant_trans_id')}"
            f"{payload.get('amount')}"
            f"{payload.get('action')}"
            f"{payload.get('sign_time')}"
        )
        expected = hashlib.md5(sign_string.encode()).hexdigest()
        return signature == expected


# ----------------------------
# Provider Factory
# ----------------------------

def get_payment_provider(provider_name: str) -> BasePaymentProvider:
    """
    Factory function to get the configured payment provider.
    Add new providers here; the service layer never changes.
    """
    from django.conf import settings

    providers = {
        "mock": lambda: MockPaymentProvider(),
        "payme": lambda: PaymeProvider(
            merchant_id=settings.PAYME_MERCHANT_ID,
            key=settings.PAYME_KEY,
            test_mode=getattr(settings, "PAYME_TEST_MODE", True),
        ),
        "click": lambda: ClickProvider(
            service_id=settings.CLICK_SERVICE_ID,
            merchant_id=settings.CLICK_MERCHANT_ID,
            secret_key=settings.CLICK_SECRET_KEY,
        ),
    }

    factory = providers.get(provider_name)
    if not factory:
        logger.warning("Unknown payment provider '%s', falling back to mock.", provider_name)
        factory = providers["mock"]

    return factory()
