"""
Core base models.
All domain models should inherit from these.
"""

import uuid

from django.db import models
from django.utils import timezone


class UUIDModel(models.Model):
    """
    Abstract base model that uses UUID as primary key.
    Prevents enumeration attacks and improves security.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        db_index=True,
    )

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """
    Abstract base model with created_at and updated_at timestamps.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class SoftDeleteManager(models.Manager):
    """Manager that filters out soft-deleted objects by default."""

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager):
    """Manager that returns all objects, including soft-deleted."""

    def get_queryset(self) -> models.QuerySet:
        return super().get_queryset()


class SoftDeleteModel(models.Model):
    """
    Abstract model with soft delete functionality.
    Records are never truly deleted — only marked as deleted.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):  # type: ignore[override]
        """Soft delete: set deleted_at instead of removing the row."""
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def hard_delete(self, using=None, keep_parents=False):
        """Actually remove the record from the database."""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class BaseModel(UUIDModel, TimeStampedModel, SoftDeleteModel):
    """
    Full-featured base model combining UUID PK, timestamps, and soft delete.
    Recommended base for all primary domain models.
    """

    class Meta:
        abstract = True
        ordering = ["-created_at"]
