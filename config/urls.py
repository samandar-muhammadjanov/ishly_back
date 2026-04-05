"""
Main URL configuration for GIG Marketplace.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views import HealthCheckView

# ----------------------------
# API v1 URL patterns
# ----------------------------
api_v1_patterns = [
    path("auth/", include("apps.accounts.urls.auth", namespace="auth")),
    path("users/", include("apps.accounts.urls.users", namespace="users")),
    path("jobs/", include("apps.jobs.urls", namespace="jobs")),
    path("wallet/", include("apps.payments.urls.wallet", namespace="wallet")),
    path("payments/", include("apps.payments.urls.payments", namespace="payments")),
    path("notifications/", include("apps.notifications.urls", namespace="notifications")),
    path("chat/", include("apps.chat.urls", namespace="chat")),
]

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),

    # API
    path("api/v1/", include((api_v1_patterns, "v1"))),

    # Health check
    path("health/", HealthCheckView.as_view(), name="health_check"),

    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Static/Media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    # Debug Toolbar
    try:
        import debug_toolbar
        urlpatterns = [
            path("__debug__/", include(debug_toolbar.urls)),
        ] + urlpatterns
    except ImportError:
        pass

# Admin customization
admin.site.site_header = "GIG Marketplace Admin"
admin.site.site_title = "GIG Marketplace"
admin.site.index_title = "Administration Dashboard"
