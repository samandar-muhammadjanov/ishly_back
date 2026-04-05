"""
Jobs service layer.
All job business logic: creation, acceptance, lifecycle, geo-filtering.
"""

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import (
    ConflictException,
    ForbiddenException,
    InsufficientBalanceException,
    JobStateException,
    NotFoundException,
    ValidationException,
)
from apps.core.utils import bounding_box, calculate_commission, haversine_distance

from .models import Job, JobCategory, JobReview, JobStatus

logger = logging.getLogger(__name__)

JOB_LIST_CACHE_TTL = getattr(settings, "JOB_LIST_CACHE_TTL", 60)


class JobService:
    """
    Handles job creation, lifecycle transitions, and business rules.
    """

    @classmethod
    @transaction.atomic
    def create_job(cls, employer, data: dict[str, Any]) -> Job:
        """
        Create a new job.

        Business rules:
        - Only employers can create jobs
        - Employer must have sufficient balance
        - Price is deducted from wallet immediately (escrow)

        Args:
            employer: The User creating the job
            data: Validated job fields from serializer
        """
        if not employer.is_employer:
            raise ForbiddenException("Only employers can create jobs.")

        price = data["price"]

        # Check wallet balance (select_for_update prevents concurrent deductions)
        wallet = (
            employer.wallet.__class__.objects
            .select_for_update()
            .get(user=employer)
        )

        if wallet.balance < price:
            raise InsufficientBalanceException(
                f"Insufficient balance. Required: {price}, Available: {wallet.balance}."
            )

        # Create the job
        job = Job.objects.create(
            employer=employer,
            **data,
        )

        # Deduct from wallet (escrow)
        from apps.payments.services import WalletService
        WalletService.deduct_for_job(wallet, job)

        logger.info(
            "Job created: %s by employer %s, price: %s",
            job.id, employer.id, price
        )

        # Notify workers async
        from apps.notifications.tasks import notify_new_job_task
        notify_new_job_task.delay(str(job.id))

        # Invalidate job list cache
        cls._invalidate_job_cache()

        return job

    @classmethod
    @transaction.atomic
    def accept_job(cls, job_id: str, worker) -> Job:
        """
        Worker accepts a job.

        Uses SELECT FOR UPDATE to prevent race conditions:
        Only one worker can accept a job even under heavy concurrent load.

        Args:
            job_id: UUID of the job to accept
            worker: The User (worker) accepting
        """
        if not worker.is_worker:
            raise ForbiddenException("Only workers can accept jobs.")

        # Lock the row before reading status
        try:
            job = (
                Job.objects
                .select_for_update(nowait=True)  # Fail fast, don't queue
                .select_related("employer")
                .get(id=job_id)
            )
        except Job.DoesNotExist:
            raise NotFoundException("Job not found.")
        except Exception:
            # Lock couldn't be acquired — another worker is accepting simultaneously
            raise ConflictException(
                "Job is currently being processed. Please try again."
            )

        # Validate current state
        if job.status != JobStatus.CREATED:
            raise JobStateException(
                f"Job cannot be accepted. Current status: {job.status}."
            )

        # Prevent employer from accepting their own job
        if job.employer == worker:
            raise ForbiddenException("You cannot accept your own job.")

        # Transition to ACCEPTED
        job.worker = worker
        job.status = JobStatus.ACCEPTED
        job.accepted_at = timezone.now()
        job.save(update_fields=["worker", "status", "accepted_at", "updated_at"])

        logger.info("Job %s accepted by worker %s", job.id, worker.id)

        # Notify employer
        from apps.notifications.tasks import notify_job_accepted_task
        notify_job_accepted_task.delay(str(job.id))

        cls._invalidate_job_cache()

        return job

    @classmethod
    @transaction.atomic
    def start_job(cls, job_id: str, worker) -> Job:
        """Worker marks job as in_progress."""
        job = cls._get_job_for_worker(job_id, worker)

        if job.status != JobStatus.ACCEPTED:
            raise JobStateException(
                f"Job must be ACCEPTED to start. Current: {job.status}."
            )

        job.status = JobStatus.IN_PROGRESS
        job.started_at = timezone.now()
        job.save(update_fields=["status", "started_at", "updated_at"])

        logger.info("Job %s started by worker %s", job.id, worker.id)
        return job

    @classmethod
    @transaction.atomic
    def complete_job(cls, job_id: str, employer) -> Job:
        """
        Employer marks job as completed.

        Triggers payment release:
        - 90% goes to worker wallet
        - 10% kept as platform commission
        """
        if not employer.is_employer:
            raise ForbiddenException("Only the employer can complete a job.")

        try:
            job = (
                Job.objects
                .select_for_update()
                .select_related("employer", "worker")
                .get(id=job_id, employer=employer)
            )
        except Job.DoesNotExist:
            raise NotFoundException("Job not found.")

        if job.status != JobStatus.IN_PROGRESS:
            raise JobStateException(
                f"Job must be IN_PROGRESS to complete. Current: {job.status}."
            )

        if not job.worker:
            raise JobStateException("Job has no assigned worker.")

        # Transition to COMPLETED
        job.status = JobStatus.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at", "updated_at"])

        # Release payment to worker
        from apps.payments.services import WalletService
        WalletService.release_job_payment(job)

        logger.info("Job %s completed. Payment released to worker %s.", job.id, job.worker.id)

        # Notify worker
        from apps.notifications.tasks import notify_job_completed_task
        notify_job_completed_task.delay(str(job.id))

        cls._invalidate_job_cache()

        return job

    @classmethod
    @transaction.atomic
    def cancel_job(cls, job_id: str, user, reason: str = "") -> Job:
        """
        Cancel a job. Can be done by employer or worker.

        Refund rules:
        - CREATED status → full refund to employer
        - ACCEPTED / IN_PROGRESS → partial refund (configurable, default full)
        """
        try:
            job = (
                Job.objects
                .select_for_update()
                .select_related("employer", "worker")
                .get(id=job_id)
            )
        except Job.DoesNotExist:
            raise NotFoundException("Job not found.")

        # Authorization
        if user not in (job.employer, job.worker):
            raise ForbiddenException("You are not authorized to cancel this job.")

        if not job.can_be_cancelled:
            raise JobStateException(
                f"Job cannot be cancelled. Current status: {job.status}."
            )

        prev_status = job.status
        job.status = JobStatus.CANCELLED
        job.cancelled_at = timezone.now()
        job.cancel_reason = reason
        job.save(update_fields=["status", "cancelled_at", "cancel_reason", "updated_at"])

        # Refund employer if cancelled before completion
        if prev_status in (JobStatus.CREATED, JobStatus.ACCEPTED, JobStatus.IN_PROGRESS):
            from apps.payments.services import WalletService
            WalletService.refund_job(job)

        logger.info("Job %s cancelled by user %s. Reason: %s", job.id, user.id, reason)
        cls._invalidate_job_cache()

        return job

    @classmethod
    def _get_job_for_worker(cls, job_id: str, worker) -> Job:
        """Helper: fetch a job and validate it belongs to the given worker."""
        try:
            return (
                Job.objects
                .select_for_update()
                .select_related("employer", "worker")
                .get(id=job_id, worker=worker)
            )
        except Job.DoesNotExist:
            raise NotFoundException("Job not found or not assigned to you.")

    @staticmethod
    def _invalidate_job_cache() -> None:
        """Invalidate all job list cache keys."""
        from apps.core.utils import invalidate_cache_pattern
        invalidate_cache_pattern("job_list")


class JobDiscoveryService:
    """
    Handles job discovery for workers: filtering, geo-search, sorting.
    Uses bounding box pre-filter + Haversine for accurate distance.
    """

    @classmethod
    def get_available_jobs(
        cls,
        lat: float | None = None,
        lon: float | None = None,
        radius_km: float | None = None,
        category_slug: str | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        sort_by: str = "-created_at",
    ):
        """
        Return available jobs (CREATED status) with optional geo/price/category filters.

        If lat/lon provided, uses bounding box pre-filter then Haversine distance.
        Results are annotated with distance_km when geo filter is active.
        """
        qs = (
            Job.objects
            .filter(status=JobStatus.CREATED)
            .select_related("employer", "category")
            .prefetch_related("images")
        )

        # Category filter
        if category_slug:
            qs = qs.filter(category__slug=category_slug)

        # Price filter
        if min_price is not None:
            qs = qs.filter(price__gte=min_price)
        if max_price is not None:
            qs = qs.filter(price__lte=max_price)

        # Geo filter using bounding box (fast DB pre-filter)
        search_radius = radius_km or settings.DEFAULT_SEARCH_RADIUS_KM
        jobs_with_distance = None

        if lat is not None and lon is not None:
            bbox = bounding_box(lat, lon, search_radius)
            qs = qs.filter(
                latitude__gte=bbox["lat_min"],
                latitude__lte=bbox["lat_max"],
                longitude__gte=bbox["lon_min"],
                longitude__lte=bbox["lon_max"],
            )

            # Compute precise Haversine distance in Python
            # For very large datasets, move this to a DB function or PostGIS
            jobs_list = list(qs)
            jobs_with_distance = []
            for job in jobs_list:
                dist = haversine_distance(lat, lon, job.latitude, job.longitude)
                if dist <= search_radius:
                    job.distance_km = round(dist, 2)  # type: ignore[attr-defined]
                    jobs_with_distance.append(job)

            # Sort by distance if requested
            if sort_by == "distance":
                jobs_with_distance.sort(key=lambda j: j.distance_km)
                return jobs_with_distance

            # Default sort after distance filter
            jobs_with_distance.sort(
                key=lambda j: j.created_at,
                reverse=(not sort_by.startswith("-")),
            )
            return jobs_with_distance

        # No geo filter — return queryset directly (paginated by DRF)
        valid_sorts = {
            "-created_at", "created_at", "-price", "price",
        }
        if sort_by in valid_sorts:
            qs = qs.order_by(sort_by)

        return qs
