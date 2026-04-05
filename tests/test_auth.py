"""
Tests for the authentication module.
Covers: OTP send/verify, JWT generation, rate limiting.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.cache import cache

from apps.accounts.models import OTPCode, User
from apps.accounts.services import AuthService, OTPService
from apps.core.exceptions import OTPException, RateLimitException


@pytest.mark.django_db
class TestSendOTPView:
    """POST /api/v1/auth/send-otp/"""

    URL = "/api/v1/auth/send-otp/"

    def test_send_otp_success(self, api_client):
        """Valid phone number should trigger OTP send and return 200."""
        with patch("apps.accounts.tasks.send_otp_sms_task.delay") as mock_task:
            resp = api_client.post(self.URL, {"phone_number": "+998901234567"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "expires_in" in data["data"]
        assert mock_task.called

    def test_send_otp_invalid_phone(self, api_client):
        """Garbage phone number should return 400."""
        resp = api_client.post(self.URL, {"phone_number": "not-a-phone"})
        assert resp.status_code == 400

    def test_send_otp_rate_limited(self, api_client):
        """Exceeding 5 OTPs/hour for the same number should return 429."""
        phone = "+998907654321"
        with patch("apps.accounts.tasks.send_otp_sms_task.delay"):
            for _ in range(5):
                api_client.post(self.URL, {"phone_number": phone})
            resp = api_client.post(self.URL, {"phone_number": phone})

        assert resp.status_code == 429


@pytest.mark.django_db
class TestVerifyOTPView:
    """POST /api/v1/auth/verify-otp/"""

    URL = "/api/v1/auth/verify-otp/"
    SEND_URL = "/api/v1/auth/send-otp/"

    def _send_and_get_otp(self, api_client, phone: str) -> str:
        with patch("apps.accounts.tasks.send_otp_sms_task.delay"):
            api_client.post(self.SEND_URL, {"phone_number": phone})
        # In dev mode, the OTP is always 123456
        return "123456"

    def test_verify_otp_creates_new_user(self, api_client):
        """First-time OTP verification should create user and return tokens."""
        phone = "+998901112233"
        otp = self._send_and_get_otp(api_client, phone)

        resp = api_client.post(self.URL, {"phone_number": phone, "code": otp})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "access" in data
        assert "refresh" in data
        assert data["is_new_user"] is True
        assert User.objects.filter(phone_number=phone).exists()

    def test_verify_otp_returns_existing_user(self, api_client, employer_user):
        """Second login should not create duplicate and return is_new_user=False."""
        phone = str(employer_user.phone_number)
        otp = self._send_and_get_otp(api_client, phone)

        resp = api_client.post(self.URL, {"phone_number": phone, "code": otp})

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_new_user"] is False
        assert User.objects.filter(phone_number=phone).count() == 1

    def test_verify_wrong_otp(self, api_client):
        """Wrong code should return 400 with clear error."""
        phone = "+998909876543"
        self._send_and_get_otp(api_client, phone)

        resp = api_client.post(self.URL, {"phone_number": phone, "code": "000000"})

        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_verify_expired_otp(self, api_client):
        """If Redis key doesn't exist (expired), return 400."""
        resp = api_client.post(
            self.URL, {"phone_number": "+998901239999", "code": "123456"}
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestOTPService:
    """Unit tests for OTPService logic."""

    def setup_method(self):
        cache.clear()

    def test_send_otp_stores_in_cache(self):
        phone = "+998901010101"
        with patch("apps.accounts.tasks.send_otp_sms_task.delay"):
            OTPService.send_otp(phone)

        from apps.core.utils import get_otp_cache_key
        assert cache.get(get_otp_cache_key(phone)) is not None

    def test_verify_correct_otp(self):
        phone = "+998901020304"
        with patch("apps.accounts.tasks.send_otp_sms_task.delay"):
            OTPService.send_otp(phone)

        # Patch cache to return fixed code
        from apps.core.utils import get_otp_cache_key
        cache.set(get_otp_cache_key(phone), {"code": "999888", "attempts": 0})

        result = OTPService.verify_otp(phone, "999888")
        assert result is True

    def test_verify_wrong_otp_increments_attempts(self):
        phone = "+998901020305"
        from apps.core.utils import get_otp_cache_key, get_otp_attempts_key
        cache.set(get_otp_cache_key(phone), {"code": "111222", "attempts": 0})

        with pytest.raises(OTPException, match="Invalid OTP"):
            OTPService.verify_otp(phone, "000000")

        assert cache.get(get_otp_attempts_key(phone)) == 1

    def test_verify_too_many_attempts_raises(self):
        phone = "+998901020306"
        from apps.core.utils import get_otp_cache_key, get_otp_attempts_key
        cache.set(get_otp_cache_key(phone), {"code": "111222", "attempts": 0})
        cache.set(get_otp_attempts_key(phone), OTPService.MAX_ATTEMPTS)

        with pytest.raises(OTPException, match="Too many"):
            OTPService.verify_otp(phone, "111222")

    def test_rate_limit_exceeded_raises(self):
        phone = "+998901020307"
        from apps.core.utils import get_otp_rate_limit_key
        cache.set(get_otp_rate_limit_key(phone), OTPService.RATE_LIMIT)

        with pytest.raises(RateLimitException):
            with patch("apps.accounts.tasks.send_otp_sms_task.delay"):
                OTPService.send_otp(phone)


@pytest.mark.django_db
class TestLogoutView:
    """POST /api/v1/auth/logout/"""

    URL = "/api/v1/auth/logout/"

    def test_logout_blacklists_token(self, employer_client, employer_user):
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(employer_user)

        resp = employer_client.post(self.URL, {"refresh": str(refresh)})

        assert resp.status_code == 200
        # Refreshing with blacklisted token should fail
        refresh_resp = employer_client.post(
            "/api/v1/auth/token/refresh/", {"refresh": str(refresh)}
        )
        assert refresh_resp.status_code == 401
