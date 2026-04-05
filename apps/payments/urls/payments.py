"""Payment provider webhook URL patterns."""

from django.urls import path

from apps.payments.views import ClickWebhookView, PaymeWebhookView

app_name = "payments"

urlpatterns = [
    path("webhook/payme/", PaymeWebhookView.as_view(), name="payme_webhook"),
    path("webhook/click/", ClickWebhookView.as_view(), name="click_webhook"),
]
