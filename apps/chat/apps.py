from django.apps import AppConfig


class ChatConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.chat"
    verbose_name = "Chat"

    def ready(self) -> None:
        from apps.chat.signals import setup_chat_signals
        setup_chat_signals()
