"""Development settings - extends base settings."""

from .base import *  # noqa: F401, F403

DEBUG = True

# Allow all hosts in development
ALLOWED_HOSTS = ["*"]

# Django Debug Toolbar
INSTALLED_APPS += ["debug_toolbar"]  # noqa: F405
MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")  # noqa: F405

INTERNAL_IPS = ["127.0.0.1", "0.0.0.0"]

# Simplified email backend for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Disable throttling in development for easier testing
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = []  # noqa: F405

# More verbose logging in development
LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405

# CORS - allow all in dev
CORS_ALLOW_ALL_ORIGINS = True

# Development OTP: use a fixed OTP for testing
DEV_FIXED_OTP = "123456"
USE_FIXED_OTP = True  # Set to False to use real OTP generation
