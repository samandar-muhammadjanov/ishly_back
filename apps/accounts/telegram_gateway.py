"""
Telegram Gateway API client.
https://core.telegram.org/gateway/api

Sends OTP verification messages directly to a user's Telegram app
using only their phone number — no bot or Telegram account required.
"""

import logging

import httpx
from django.conf import settings

from apps.core.exceptions import ServiceUnavailableException

logger = logging.getLogger(__name__)

GATEWAY_BASE_URL = "https://gatewayapi.telegram.org"


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.TELEGRAM_GATEWAY_TOKEN}"}


def send_otp(phone: str) -> dict:
    """
    POST /sendVerificationMessage

    Asks Telegram to send an OTP to the given phone number.
    Returns the result dict containing request_id on success.
    Raises ServiceUnavailableException on network or API failure.
    """
    try:
        resp = httpx.post(
            f"{GATEWAY_BASE_URL}/sendVerificationMessage",
            json={"phone_number": phone, "code_length": 6, "ttl": 300},
            headers=_headers(),
            timeout=10,
        )
        data = resp.json()
    except httpx.RequestError as exc:
        logger.error("Telegram Gateway network error on send: %s", exc)
        raise ServiceUnavailableException("Could not reach Telegram Gateway.")

    if not data.get("ok"):
        logger.error("Telegram Gateway sendVerificationMessage failed: %s", data)
        raise ServiceUnavailableException(
            data.get("error", "Telegram Gateway returned an error.")
        )

    return data["result"]


def verify_otp(request_id: str, code: str) -> bool:
    """
    POST /checkVerificationStatus

    Returns True if the code is valid for the given request_id.
    Returns False on invalid code or unexpected API response.
    Raises ServiceUnavailableException on network failure.
    """
    try:
        resp = httpx.post(
            f"{GATEWAY_BASE_URL}/checkVerificationStatus",
            json={"request_id": request_id, "code": code},
            headers=_headers(),
            timeout=10,
        )
        data = resp.json()
    except httpx.RequestError as exc:
        logger.error("Telegram Gateway network error on verify: %s", exc)
        raise ServiceUnavailableException("Could not reach Telegram Gateway.")

    if not data.get("ok"):
        logger.warning("Telegram Gateway checkVerificationStatus failed: %s", data)
        return False

    verification_status = data.get("result", {}).get("verification_status", {})
    return verification_status.get("status") == "code_valid"


def revoke_otp(request_id: str) -> None:
    """
    POST /revokeVerificationMessage

    Revokes a previously sent OTP. Best-effort — failures are logged but ignored.
    Call this before issuing a new OTP to the same phone number.
    """
    try:
        httpx.post(
            f"{GATEWAY_BASE_URL}/revokeVerificationMessage",
            json={"request_id": request_id},
            headers=_headers(),
            timeout=10,
        )
    except Exception as exc:
        logger.warning("Failed to revoke Telegram OTP %s: %s", request_id, exc)
