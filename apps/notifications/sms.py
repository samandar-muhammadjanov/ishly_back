"""
SMS provider abstraction layer.
Decouples OTP sending from any specific SMS gateway.
Add new providers by implementing BaseSMSProvider.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ----------------------------
# Abstract Base
# ----------------------------

class BaseSMSProvider(ABC):
    """All SMS providers must implement this interface."""

    @abstractmethod
    def send_otp(self, phone_number: str, code: str) -> dict[str, Any]:
        """
        Send an OTP SMS.

        Returns:
            {"status": "sent", "message_id": "...", "provider": "..."}
        Raises:
            Exception on delivery failure (caller handles retry logic).
        """
        ...

    @abstractmethod
    def send_sms(self, phone_number: str, message: str) -> dict[str, Any]:
        """Send a generic SMS message."""
        ...


# ----------------------------
# Mock Provider (dev / tests)
# ----------------------------

class MockSMSProvider(BaseSMSProvider):
    """
    Logs OTP to console instead of sending real SMS.
    Used in development and CI environments.
    """

    def send_otp(self, phone_number: str, code: str) -> dict[str, Any]:
        logger.info(
            "📱 [MockSMS] OTP for %s: %s  ← Use this in Swagger/Postman",
            phone_number, code,
        )
        return {
            "status": "sent",
            "message_id": f"mock_{phone_number}_{code}",
            "provider": "mock",
        }

    def send_sms(self, phone_number: str, message: str) -> dict[str, Any]:
        logger.info("📱 [MockSMS] To %s: %s", phone_number, message)
        return {"status": "sent", "message_id": f"mock_{phone_number}", "provider": "mock"}


# ----------------------------
# Eskiz Provider (Uzbekistan)
# ----------------------------

class EskizSMSProvider(BaseSMSProvider):
    """
    Eskiz.uz SMS gateway — primary provider for Uzbekistan.
    Docs: https://documenter.getpostman.com/view/663428/RzfmES4z

    Token-based auth with auto-refresh.
    """

    BASE_URL = "https://notify.eskiz.uz/api"
    _token: str | None = None

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password

    def _authenticate(self) -> str:
        """Obtain or refresh authentication token."""
        import requests
        resp = requests.post(
            f"{self.BASE_URL}/auth/login",
            data={"email": self.email, "password": self.password},
            timeout=10,
        )
        resp.raise_for_status()
        self._token = resp.json()["data"]["token"]
        return self._token

    def _get_token(self) -> str:
        if not self._token:
            return self._authenticate()
        return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_token()}"}

    def send_otp(self, phone_number: str, code: str) -> dict[str, Any]:
        message = f"GIG Marketplace: Your verification code is {code}. Valid for 2 minutes."
        return self.send_sms(phone_number, message)

    def send_sms(self, phone_number: str, message: str) -> dict[str, Any]:
        import requests

        # Normalize phone: Eskiz expects without leading +
        normalized = phone_number.replace("+", "")

        try:
            resp = requests.post(
                f"{self.BASE_URL}/message/sms/send",
                data={
                    "mobile_phone": normalized,
                    "message": message,
                    "from": "4546",  # Eskiz sender name
                },
                headers=self._headers(),
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()

            logger.info("Eskiz SMS sent to %s: %s", phone_number, data)
            return {
                "status": "sent",
                "message_id": str(data.get("id", "")),
                "provider": "eskiz",
            }
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 401:
                # Token expired — refresh and retry once
                self._token = None
                return self.send_sms(phone_number, message)
            logger.error("Eskiz SMS failed for %s: %s", phone_number, e)
            raise
        except Exception as e:
            logger.error("Eskiz SMS error for %s: %s", phone_number, e)
            raise


# ----------------------------
# Provider Factory
# ----------------------------

def get_sms_provider() -> BaseSMSProvider:
    """
    Return the configured SMS provider instance.
    Reads SMS_PROVIDER from Django settings.
    """
    from django.conf import settings

    provider_name = getattr(settings, "SMS_PROVIDER", "mock")

    if provider_name == "eskiz":
        email = getattr(settings, "ESKIZ_EMAIL", "")
        password = getattr(settings, "ESKIZ_PASSWORD", "")
        if not email or not password:
            logger.warning("Eskiz credentials missing, falling back to mock SMS.")
            return MockSMSProvider()
        return EskizSMSProvider(email=email, password=password)

    # Default: mock
    return MockSMSProvider()
