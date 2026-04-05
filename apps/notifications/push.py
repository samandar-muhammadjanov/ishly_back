"""
Push notification provider abstraction.
Supports Firebase FCM (production) and Mock (development).
"""

import logging
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ----------------------------
# Abstract Base
# ----------------------------

class BasePushProvider(ABC):
    """Interface for push notification providers."""

    @abstractmethod
    def send_to_token(
        self,
        token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a push notification to a single device token."""
        ...

    @abstractmethod
    def send_to_tokens(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a push notification to multiple device tokens (multicast)."""
        ...


# ----------------------------
# Mock Provider
# ----------------------------

class MockPushProvider(BasePushProvider):
    """Logs notifications instead of sending. Used in development."""

    def send_to_token(
        self,
        token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "🔔 [MockPush] To token %s...: %s — %s | data=%s",
            token[:20], title, body, data,
        )
        return {"success": 1, "failure": 0, "provider": "mock"}

    def send_to_tokens(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        logger.info(
            "🔔 [MockPush] Multicast to %d tokens: %s — %s",
            len(tokens), title, body,
        )
        return {"success": len(tokens), "failure": 0, "provider": "mock"}


# ----------------------------
# Firebase FCM Provider
# ----------------------------

class FirebasePushProvider(BasePushProvider):
    """
    Firebase Cloud Messaging push notification provider.
    Requires firebase-admin SDK and service account credentials.

    Setup:
      1. Download credentials JSON from Firebase Console
      2. Set FIREBASE_CREDENTIALS_FILE in .env
      3. Set NOTIFICATION_PROVIDER=firebase in .env
    """

    _app = None  # Firebase app singleton

    def __init__(self, credentials_file: str):
        self.credentials_file = credentials_file
        self._initialize()

    def _initialize(self) -> None:
        """Initialize Firebase app (singleton pattern)."""
        if FirebasePushProvider._app is not None:
            return
        try:
            import firebase_admin
            from firebase_admin import credentials
            cred = credentials.Certificate(self.credentials_file)
            FirebasePushProvider._app = firebase_admin.initialize_app(cred)
            logger.info("Firebase app initialized from %s", self.credentials_file)
        except ImportError:
            logger.error(
                "firebase-admin not installed. "
                "Run: pip install firebase-admin"
            )
            raise
        except Exception as e:
            logger.error("Firebase initialization failed: %s", e)
            raise

    def send_to_token(
        self,
        token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            from firebase_admin import messaging
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                token=token,
                android=messaging.AndroidConfig(priority="high"),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(sound="default")
                    )
                ),
            )
            response = messaging.send(message)
            logger.info("FCM message sent: %s", response)
            return {"success": 1, "failure": 0, "message_id": response}
        except Exception as e:
            logger.error("FCM send_to_token failed: %s", e)
            return {"success": 0, "failure": 1, "error": str(e)}

    def send_to_tokens(
        self,
        tokens: list[str],
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not tokens:
            return {"success": 0, "failure": 0}

        try:
            from firebase_admin import messaging
            message = messaging.MulticastMessage(
                notification=messaging.Notification(title=title, body=body),
                data={k: str(v) for k, v in (data or {}).items()},
                tokens=tokens,
                android=messaging.AndroidConfig(priority="high"),
            )
            response = messaging.send_each_for_multicast(message)
            logger.info(
                "FCM multicast: success=%d, failure=%d",
                response.success_count, response.failure_count,
            )
            return {
                "success": response.success_count,
                "failure": response.failure_count,
            }
        except Exception as e:
            logger.error("FCM multicast failed: %s", e)
            return {"success": 0, "failure": len(tokens), "error": str(e)}


# ----------------------------
# Provider Factory
# ----------------------------

def get_push_provider() -> BasePushProvider:
    """Return the configured push notification provider."""
    from django.conf import settings

    provider_name = getattr(settings, "NOTIFICATION_PROVIDER", "mock")

    if provider_name == "firebase":
        credentials_file = getattr(settings, "FIREBASE_CREDENTIALS_FILE", "")
        try:
            return FirebasePushProvider(credentials_file=credentials_file)
        except Exception:
            logger.warning("Firebase init failed, falling back to mock push.")
            return MockPushProvider()

    return MockPushProvider()
