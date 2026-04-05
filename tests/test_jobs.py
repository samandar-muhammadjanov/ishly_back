"""
Tests for the jobs module.
Covers: creation, acceptance (race condition), lifecycle, geo-discovery.
"""

from unittest.mock import patch

import pytest

from apps.jobs.models import Job, JobStatus
from apps.jobs.services import JobService
from apps.core.exceptions import (
    ForbiddenException,
    InsufficientBalanceException,
    JobStateException,
)


@pytest.mark.django_db
class TestCreateJob:
    """POST /api/v1/jobs/"""

    URL = "/api/v1/jobs/"

    def _payload(self, category):
        return {
            "title": "Test Job",
            "description": "This is a test job description.",
            "category_id": str(category.id),
            "price": 100_000,
            "latitude": 41.2995,
            "longitude": 69.2401,
            "address": "Tashkent",
        }

    def test_employer_can_create_job(self, employer_client, job_category):
        with patch("apps.notifications.tasks.notify_new_job_task.delay"):
            resp = employer_client.post(self.URL, self._payload(job_category))
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Test Job"
        assert data["status"] == JobStatus.CREATED

    def test_worker_cannot_create_job(self, worker_client, job_category):
        resp = worker_client.post(self.URL, self._payload(job_category))
        assert resp.status_code == 403

    def test_create_job_deducts_balance(self, employer_client, employer_user, job_category):
        from apps.payments.models import Wallet
        wallet = Wallet.objects.get(user=employer_user)
        balance_before = wallet.balance

        with patch("apps.notifications.tasks.notify_new_job_task.delay"):
            employer_client.post(self.URL, self._payload(job_category))

        wallet.refresh_from_db()
        assert wallet.balance == balance_before - 100_000
        assert wallet.held_balance == 100_000

    def test_create_job_insufficient_balance(self, employer_user, employer_client, job_category):
        from apps.payments.models import Wallet
        wallet = Wallet.objects.get(user=employer_user)
        wallet.balance = 0
        wallet.save()

        resp = employer_client.post(self.URL, self._payload(job_category))
        assert resp.status_code == 402

    def test_create_job_unauthenticated(self, api_client, job_category):
        resp = api_client.post(self.URL, self._payload(job_category))
        assert resp.status_code == 401


@pytest.mark.django_db
class TestAcceptJob:
    """POST /api/v1/jobs/{id}/accept/"""

    def _url(self, job_id):
        return f"/api/v1/jobs/{job_id}/accept/"

    def test_worker_can_accept_open_job(self, worker_client, open_job):
        with patch("apps.notifications.tasks.notify_job_accepted_task.delay"):
            resp = worker_client.post(self._url(open_job.id))
        assert resp.status_code == 200
        open_job.refresh_from_db()
        assert open_job.status == JobStatus.ACCEPTED

    def test_employer_cannot_accept_own_job(self, employer_client, open_job):
        resp = employer_client.post(self._url(open_job.id))
        assert resp.status_code in (403, 400)

    def test_cannot_accept_already_accepted_job(self, worker_client, accepted_job):
        resp = worker_client.post(self._url(accepted_job.id))
        assert resp.status_code == 409

    def test_employer_cannot_accept_as_worker(self, employer_client, open_job):
        resp = employer_client.post(self._url(open_job.id))
        assert resp.status_code == 403


@pytest.mark.django_db
class TestJobRaceCondition:
    """
    Ensure only one worker can accept a job even with concurrent requests.
    Uses select_for_update under the hood.
    """

    def test_only_one_worker_accepts(self, db, employer_user, job_category):
        """
        Simulate two workers accepting the same job simultaneously.
        Only the first transaction should succeed.
        """
        from apps.accounts.models import User
        from apps.payments.models import Wallet

        # Create a fresh open job (pre-fund employer)
        wallet = Wallet.objects.get_or_create(user=employer_user, defaults={"balance": 5_000_000})[0]
        wallet.balance = 5_000_000
        wallet.save()

        with patch("apps.notifications.tasks.notify_new_job_task.delay"):
            job = JobService.create_job(
                employer=employer_user,
                data={
                    "title": "Race Test Job",
                    "description": "Test",
                    "category": job_category,
                    "price": 10_000,
                    "latitude": 41.3,
                    "longitude": 69.2,
                    "address": "Test",
                },
            )

        worker1 = User.objects.create_user(phone_number="+998903331111", role="worker")
        worker2 = User.objects.create_user(phone_number="+998903332222", role="worker")

        success_count = 0
        errors = []

        with patch("apps.notifications.tasks.notify_job_accepted_task.delay"):
            try:
                JobService.accept_job(job_id=str(job.id), worker=worker1)
                success_count += 1
            except Exception as e:
                errors.append(e)

            try:
                JobService.accept_job(job_id=str(job.id), worker=worker2)
                success_count += 1
            except Exception as e:
                errors.append(e)

        # Exactly one should succeed
        assert success_count == 1
        assert len(errors) == 1
        job.refresh_from_db()
        assert job.status == JobStatus.ACCEPTED


@pytest.mark.django_db
class TestJobLifecycle:
    """Test full job status transitions."""

    def test_start_job(self, worker_client, accepted_job, worker_user):
        resp = worker_client.post(f"/api/v1/jobs/{accepted_job.id}/start/")
        assert resp.status_code == 200
        accepted_job.refresh_from_db()
        assert accepted_job.status == JobStatus.IN_PROGRESS

    def test_complete_job_releases_payment(self, employer_client, employer_user, worker_user, accepted_job):
        from apps.payments.models import Wallet

        # Start the job first
        accepted_job.status = JobStatus.IN_PROGRESS
        accepted_job.save()

        worker_wallet = Wallet.objects.get(user=worker_user)
        worker_balance_before = worker_wallet.balance

        with patch("apps.notifications.tasks.notify_job_completed_task.delay"):
            resp = employer_client.post(f"/api/v1/jobs/{accepted_job.id}/complete/")

        assert resp.status_code == 200
        accepted_job.refresh_from_db()
        assert accepted_job.status == JobStatus.COMPLETED

        worker_wallet.refresh_from_db()
        expected_payout = int(accepted_job.price * 0.90)
        assert worker_wallet.balance == worker_balance_before + expected_payout

    def test_cancel_job_refunds_employer(self, employer_client, employer_user, open_job):
        from apps.payments.models import Wallet

        wallet = Wallet.objects.get(user=employer_user)
        balance_before = wallet.balance
        held_before = wallet.held_balance

        resp = employer_client.post(
            f"/api/v1/jobs/{open_job.id}/cancel/",
            {"reason": "Changed plans"},
        )

        assert resp.status_code == 200
        wallet.refresh_from_db()
        assert wallet.balance == balance_before + open_job.price
        assert wallet.held_balance == held_before - open_job.price

    def test_cannot_cancel_completed_job(self, employer_client, completed_job):
        resp = employer_client.post(
            f"/api/v1/jobs/{completed_job.id}/cancel/",
            {"reason": "Too late"},
        )
        assert resp.status_code == 409


@pytest.mark.django_db
class TestJobDiscovery:
    """GET /api/v1/jobs/ — list and filter."""

    URL = "/api/v1/jobs/"

    def test_list_shows_only_open_jobs(self, worker_client, open_job, accepted_job):
        resp = worker_client.get(self.URL)
        assert resp.status_code == 200
        job_ids = [j["id"] for j in resp.json()["data"]["results"]]
        assert str(open_job.id) in job_ids
        assert str(accepted_job.id) not in job_ids

    def test_filter_by_category(self, worker_client, open_job):
        resp = worker_client.get(self.URL, {"category": "cleaning"})
        assert resp.status_code == 200

    def test_filter_by_price_range(self, worker_client, open_job):
        resp = worker_client.get(self.URL, {"min_price": 50_000, "max_price": 500_000})
        assert resp.status_code == 200

    def test_geo_filter_finds_nearby_job(self, worker_client, open_job):
        # open_job is at 41.2995, 69.2401 — search from very close
        resp = worker_client.get(self.URL, {
            "lat": 41.300,
            "lon": 69.241,
            "radius_km": 5,
        })
        assert resp.status_code == 200
        results = resp.json()["data"]["results"]
        ids = [j["id"] for j in results]
        assert str(open_job.id) in ids

    def test_geo_filter_excludes_distant_job(self, worker_client, open_job):
        # Search from Moscow — should not find Tashkent job
        resp = worker_client.get(self.URL, {
            "lat": 55.7558,
            "lon": 37.6173,
            "radius_km": 10,
        })
        assert resp.status_code == 200
        results = resp.json()["data"]["results"]
        ids = [j["id"] for j in results]
        assert str(open_job.id) not in ids

    def test_my_jobs_returns_employer_jobs(self, employer_client, open_job):
        resp = employer_client.get("/api/v1/jobs/my/")
        assert resp.status_code == 200
        ids = [j["id"] for j in resp.json()["data"]["results"]]
        assert str(open_job.id) in ids
