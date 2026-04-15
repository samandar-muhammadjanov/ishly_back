"""
Jobs models.
Core domain: Job lifecycle, categories, geo-location.
"""

from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.accounts.models import User


class JobStatus(models.TextChoices):
    CREATED = "created", "Created"
    ACCEPTED = "accepted", "Accepted"
    IN_PROGRESS = "in_progress", "In Progress"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class JobCategory(models.Model):
    """
    Predefined job categories (e.g., Cleaning, Delivery, Moving).
    Managed via admin panel.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    icon = models.FileField(upload_to="categories/icons/", blank=True, help_text="Upload an SVG or image file")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "jobs_categories"
        verbose_name = "Job Category"
        verbose_name_plural = "Job Categories"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class Job(models.Model):
    """
    Core Job model representing a gig posted by an employer.

    Lifecycle:
      created → accepted → in_progress → completed
                         ↘ cancelled (any state except completed)

    Key design decisions:
    - price stored in smallest currency unit (tiyin/cents) as integer
      to avoid floating-point rounding errors in financial calculations
    - lat/lon stored as plain floats (sufficient for ~1m accuracy)
    - worker FK is null until a worker accepts the job
    - select_for_update() used in accept flow to prevent race conditions
    """

    # Parties
    employer = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="posted_jobs",
        db_index=True,
    )
    worker = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="accepted_jobs",
        null=True,
        blank=True,
        db_index=True,
    )

    # Job details
    title = models.CharField(max_length=200, db_index=True)
    description = models.TextField(max_length=2000)
    category = models.ForeignKey(
        JobCategory,
        on_delete=models.PROTECT,
        related_name="jobs",
        db_index=True,
    )
    price = models.PositiveIntegerField(
        help_text="Job price in tiyin (1 UZS = 100 tiyin)",
        validators=[MinValueValidator(100)],
    )

    # Location
    latitude = models.FloatField(
        validators=[MinValueValidator(-90.0), MaxValueValidator(90.0)],
    )
    longitude = models.FloatField(
        validators=[MinValueValidator(-180.0), MaxValueValidator(180.0)],
    )
    address = models.CharField(max_length=500)

    # Status
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.CREATED,
        db_index=True,
    )

    # Scheduling
    scheduled_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the worker should arrive",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.TextField(blank=True)

    class Meta:
        db_table = "jobs_jobs"
        verbose_name = "Job"
        verbose_name_plural = "Jobs"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["employer", "status"]),
            models.Index(fields=["worker", "status"]),
            models.Index(fields=["category", "status"]),
            models.Index(fields=["latitude", "longitude"]),
            models.Index(fields=["price"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} [{self.status}]"

    @property
    def price_uzs(self) -> Decimal:
        """Convert from tiyin to UZS for display."""
        return Decimal(self.price) / 100

    @property
    def is_available(self) -> bool:
        """A job is available to accept if it's in CREATED status."""
        return self.status == JobStatus.CREATED

    @property
    def can_be_cancelled(self) -> bool:
        return self.status not in (JobStatus.COMPLETED, JobStatus.CANCELLED)


class JobImage(models.Model):
    """Optional images attached to a job listing."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="jobs/%Y/%m/")
    sort_order = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "jobs_images"
        ordering = ["sort_order"]

    def __str__(self) -> str:
        return f"Image for job {self.job_id}"


class JobReview(models.Model):
    """
    Review left by employer or worker after job completion.
    Each party can leave one review per job.
    """

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="reviews")
    reviewer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="given_reviews"
    )
    reviewee = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_reviews"
    )
    rating = models.DecimalField(
        max_digits=3, decimal_places=1,
        validators=[MinValueValidator(Decimal("1.0")), MaxValueValidator(Decimal("5.0"))],
    )
    comment = models.TextField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "jobs_reviews"
        verbose_name = "Job Review"
        unique_together = [("job", "reviewer")]  # One review per party per job
        indexes = [
            models.Index(fields=["reviewee", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"Review by {self.reviewer} on job {self.job_id}"
