"""
Shared pytest fixtures for all tests.
"""

from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken


# ----------------------------
# User Fixtures
# ----------------------------

@pytest.fixture
def api_client():
    """Unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def employer_user(db):
    """A fully set-up employer user with wallet."""
    from apps.accounts.models import User
    from apps.payments.models import Wallet

    user = User.objects.create_user(
        phone_number="+998901111111",
        role="employer",
        name="Test Employer",
    )
    Wallet.objects.get_or_create(user=user, defaults={"balance": 10_000_000})
    return user


@pytest.fixture
def worker_user(db):
    """A fully set-up worker user with wallet."""
    from apps.accounts.models import User
    from apps.payments.models import Wallet

    user = User.objects.create_user(
        phone_number="+998902222222",
        role="worker",
        name="Test Worker",
    )
    Wallet.objects.get_or_create(user=user, defaults={"balance": 0})
    return user


@pytest.fixture
def employer_client(employer_user):
    """Authenticated API client for employer."""
    client = APIClient()
    refresh = RefreshToken.for_user(employer_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


@pytest.fixture
def worker_client(worker_user):
    """Authenticated API client for worker."""
    client = APIClient()
    refresh = RefreshToken.for_user(worker_user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
    return client


# ----------------------------
# Job Fixtures
# ----------------------------

@pytest.fixture
def job_category(db):
    """A single active job category."""
    from apps.jobs.models import JobCategory
    return JobCategory.objects.create(
        name="Cleaning",
        slug="cleaning",
        icon="🧹",
        is_active=True,
    )


@pytest.fixture
def open_job(db, employer_user, job_category):
    """An open (CREATED) job with escrow deducted from employer wallet."""
    from apps.jobs.models import Job, JobStatus
    from apps.payments.models import Wallet

    price = 100_000  # 1,000 UZS

    # Deduct from wallet (simulates job creation)
    wallet = Wallet.objects.get(user=employer_user)
    wallet.balance -= price
    wallet.held_balance += price
    wallet.save()

    return Job.objects.create(
        employer=employer_user,
        title="Clean my apartment",
        description="Full deep clean needed.",
        category=job_category,
        price=price,
        latitude=41.2995,
        longitude=69.2401,
        address="Yunusabad, Tashkent",
        status=JobStatus.CREATED,
    )


@pytest.fixture
def accepted_job(open_job, worker_user):
    """A job that has been accepted by a worker."""
    from apps.jobs.models import JobStatus
    open_job.worker = worker_user
    open_job.status = JobStatus.ACCEPTED
    open_job.accepted_at = timezone.now()
    open_job.save()
    return open_job


@pytest.fixture
def completed_job(accepted_job):
    """A completed job."""
    from apps.jobs.models import JobStatus
    accepted_job.status = JobStatus.IN_PROGRESS
    accepted_job.started_at = timezone.now()
    accepted_job.save()
    accepted_job.status = JobStatus.COMPLETED
    accepted_job.completed_at = timezone.now()
    accepted_job.save()
    return accepted_job
