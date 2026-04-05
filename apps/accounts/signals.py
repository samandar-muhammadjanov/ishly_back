"""
Accounts signals.
Auto-creates related objects when a user is created.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import User

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_user_wallet(sender, instance: User, created: bool, **kwargs) -> None:
    """
    Automatically create a Wallet for every new user.
    Called immediately after User.save() when created=True.
    """
    if created:
        try:
            from apps.payments.models import Wallet
            Wallet.objects.get_or_create(user=instance)
            logger.info("Wallet created for user %s", instance.id)
        except Exception as e:
            logger.error("Failed to create wallet for user %s: %s", instance.id, e)
