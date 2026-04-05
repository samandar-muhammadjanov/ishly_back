"""
Jobs views.
REST endpoints for job creation, discovery, and lifecycle management.
"""

import logging

from django.core.cache import cache
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.core.exceptions import ForbiddenException
from apps.core.pagination import StandardResultsPagination
from apps.core.permissions import IsActiveUser, IsEmployer, IsWorker

from .models import Job, JobCategory, JobStatus
from .serializers import (
    CancelJobSerializer,
    CreateJobSerializer,
    JobCategorySerializer,
    JobDetailSerializer,
    JobFilterSerializer,
    JobListSerializer,
)
from .services import JobDiscoveryService, JobService

logger = logging.getLogger(__name__)


class JobCategoryViewSet(ModelViewSet):
    """
    GET /jobs/categories/ — list all active categories
    GET /jobs/categories/{id}/ — single category
    """

    queryset = JobCategory.objects.filter(is_active=True)
    serializer_class = JobCategorySerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None  # Return full list (small dataset)
    http_method_names = ["get"]

    @extend_schema(tags=["Jobs"], summary="List job categories")
    def list(self, request: Request, *args, **kwargs) -> Response:
        # Cache categories — they change rarely
        cache_key = "job_categories"
        data = cache.get(cache_key)
        if data is None:
            qs = self.get_queryset()
            data = JobCategorySerializer(qs, many=True).data
            cache.set(cache_key, data, timeout=3600)  # 1 hour
        return Response(data)


class JobViewSet(ModelViewSet):
    """
    Main job resource.

    GET    /jobs/           — List available jobs (workers)
    POST   /jobs/           — Create job (employers only)
    GET    /jobs/{id}/      — Job detail
    PATCH  /jobs/{id}/      — Update job (employer, only CREATED status)
    DELETE /jobs/{id}/      — Cancel job

    Action endpoints:
    POST /jobs/{id}/accept/     — Worker accepts job
    POST /jobs/{id}/start/      — Worker starts job
    POST /jobs/{id}/complete/   — Employer completes job
    POST /jobs/{id}/cancel/     — Cancel job with reason
    GET  /jobs/my/              — Jobs for the authenticated user
    """

    permission_classes = [IsAuthenticated, IsActiveUser]
    pagination_class = StandardResultsPagination

    def get_serializer_class(self):
        if self.action == "create":
            return CreateJobSerializer
        if self.action in ("retrieve", "accept", "start", "complete"):
            return JobDetailSerializer
        return JobListSerializer

    def get_queryset(self):
        return (
            Job.objects
            .select_related("employer", "worker", "category")
            .prefetch_related("images")
            .order_by("-created_at")
        )

    # ------------------------------------------------------------------
    # List — discovery for workers
    # ------------------------------------------------------------------
    @extend_schema(
        tags=["Jobs"],
        summary="List available jobs",
        parameters=[
            OpenApiParameter("lat", float, description="Worker latitude"),
            OpenApiParameter("lon", float, description="Worker longitude"),
            OpenApiParameter("radius_km", float, description="Search radius (km)"),
            OpenApiParameter("category", str, description="Category slug"),
            OpenApiParameter("min_price", int),
            OpenApiParameter("max_price", int),
            OpenApiParameter(
                "sort_by",
                str,
                enum=["-created_at", "created_at", "-price", "price", "distance"],
            ),
        ],
    )
    def list(self, request: Request, *args, **kwargs) -> Response:
        filter_serializer = JobFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        params = filter_serializer.validated_data

        jobs = JobDiscoveryService.get_available_jobs(
            lat=params.get("lat"),
            lon=params.get("lon"),
            radius_km=params.get("radius_km"),
            category_slug=params.get("category"),
            min_price=params.get("min_price"),
            max_price=params.get("max_price"),
            sort_by=params.get("sort_by", "-created_at"),
        )

        # Paginate (works for both queryset and list)
        page = self.paginate_queryset(jobs)
        if page is not None:
            serializer = JobListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = JobListSerializer(jobs, many=True)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    @extend_schema(tags=["Jobs"], summary="Create a job (employers only)")
    def create(self, request: Request, *args, **kwargs) -> Response:
        if not request.user.is_employer:
            raise ForbiddenException("Only employers can create jobs.")

        serializer = CreateJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        job = JobService.create_job(
            employer=request.user,
            data=serializer.validated_data,
        )
        return Response(
            JobDetailSerializer(job).data,
            status=status.HTTP_201_CREATED,
        )

    # ------------------------------------------------------------------
    # Retrieve
    # ------------------------------------------------------------------
    @extend_schema(tags=["Jobs"], summary="Get job details")
    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        job = self.get_object()
        serializer = JobDetailSerializer(job)
        return Response(serializer.data)

    # ------------------------------------------------------------------
    # My Jobs
    # ------------------------------------------------------------------
    @extend_schema(tags=["Jobs"], summary="List my jobs (as employer or worker)")
    @action(detail=False, methods=["get"], url_path="my")
    def my_jobs(self, request: Request) -> Response:
        user = request.user
        if user.is_employer:
            qs = self.get_queryset().filter(employer=user)
        else:
            qs = self.get_queryset().filter(worker=user)

        status_filter = request.query_params.get("status")
        if status_filter and status_filter in JobStatus.values:
            qs = qs.filter(status=status_filter)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = JobListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        return Response(JobListSerializer(qs, many=True).data)

    # ------------------------------------------------------------------
    # Accept
    # ------------------------------------------------------------------
    @extend_schema(
        tags=["Jobs"],
        summary="Accept a job (workers only)",
        request=None,
        responses={200: JobDetailSerializer},
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsWorker])
    def accept(self, request: Request, pk=None) -> Response:
        job = JobService.accept_job(job_id=pk, worker=request.user)
        return Response(JobDetailSerializer(job).data)

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------
    @extend_schema(tags=["Jobs"], summary="Mark job as in-progress (worker only)")
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsWorker])
    def start(self, request: Request, pk=None) -> Response:
        job = JobService.start_job(job_id=pk, worker=request.user)
        return Response(JobDetailSerializer(job).data)

    # ------------------------------------------------------------------
    # Complete
    # ------------------------------------------------------------------
    @extend_schema(tags=["Jobs"], summary="Mark job as completed (employer only)")
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsEmployer])
    def complete(self, request: Request, pk=None) -> Response:
        job = JobService.complete_job(job_id=pk, employer=request.user)
        return Response(JobDetailSerializer(job).data)

    # ------------------------------------------------------------------
    # Cancel
    # ------------------------------------------------------------------
    @extend_schema(
        tags=["Jobs"],
        summary="Cancel a job",
        request=CancelJobSerializer,
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request: Request, pk=None) -> Response:
        serializer = CancelJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        job = JobService.cancel_job(
            job_id=pk,
            user=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(JobDetailSerializer(job).data)

    # ------------------------------------------------------------------
    # Disallow unsafe methods on discovery endpoint
    # ------------------------------------------------------------------
    def update(self, request: Request, *args, **kwargs) -> Response:
        raise ForbiddenException("Use specific action endpoints.")

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        return self.cancel(request, pk=kwargs.get("pk"))
