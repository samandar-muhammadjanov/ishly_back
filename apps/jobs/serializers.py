"""Jobs serializers."""

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.accounts.serializers import UserPublicSerializer

from .models import Job, JobCategory, JobImage, JobReview, JobStatus


class JobCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = JobCategory
        fields = ["id", "name", "slug", "icon", "description"]


class JobImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobImage
        fields = ["id", "image", "sort_order"]


class JobListSerializer(serializers.ModelSerializer):
    """Compact serializer for job lists — minimal fields for performance."""

    category = JobCategorySerializer(read_only=True)
    distance_km = serializers.SerializerMethodField()
    price_uzs = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "title", "category", "price", "price_uzs",
            "address", "latitude", "longitude",
            "status", "scheduled_time", "created_at",
            "distance_km",
        ]

    def get_distance_km(self, obj: Job) -> float | None:
        return getattr(obj, "distance_km", None)

    def get_price_uzs(self, obj: Job) -> str:
        return f"{obj.price_uzs:,.0f} UZS"


class JobDetailSerializer(serializers.ModelSerializer):
    """Full job detail serializer."""

    category = JobCategorySerializer(read_only=True)
    employer = UserPublicSerializer(read_only=True)
    worker = UserPublicSerializer(read_only=True)
    images = JobImageSerializer(many=True, read_only=True)
    price_uzs = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "title", "description", "category",
            "price", "price_uzs",
            "latitude", "longitude", "address",
            "status", "employer", "worker",
            "scheduled_time",
            "images",
            "created_at", "updated_at",
            "accepted_at", "started_at", "completed_at",
            "distance_km",
        ]

    def get_price_uzs(self, obj: Job) -> str:
        return f"{obj.price_uzs:,.0f} UZS"

    def get_distance_km(self, obj: Job) -> float | None:
        return getattr(obj, "distance_km", None)


class CreateJobSerializer(serializers.ModelSerializer):
    """Request body for POST /jobs/"""

    category_id = serializers.PrimaryKeyRelatedField(
        queryset=JobCategory.objects.filter(is_active=True),
        source="category",
    )
    image_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        write_only=True,
        help_text="Optional list of pre-uploaded image UUIDs",
    )

    class Meta:
        model = Job
        fields = [
            "title", "description", "category_id",
            "price", "latitude", "longitude", "address",
            "scheduled_time", "image_ids",
        ]

    def validate_price(self, value: int) -> int:
        if value < 100:
            raise serializers.ValidationError(
                "Minimum job price is 100 tiyin (1 UZS)."
            )
        return value

    def validate_latitude(self, value: float) -> float:
        if not -90 <= value <= 90:
            raise serializers.ValidationError("Latitude must be between -90 and 90.")
        return value

    def validate_longitude(self, value: float) -> float:
        if not -180 <= value <= 180:
            raise serializers.ValidationError("Longitude must be between -180 and 180.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        # Remove image_ids before passing to service (handled separately)
        attrs.pop("image_ids", None)
        return attrs


class CancelJobSerializer(serializers.Serializer):
    reason = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        default="",
    )


class JobFilterSerializer(serializers.Serializer):
    """Query params for GET /jobs/"""

    lat = serializers.FloatField(required=False)
    lon = serializers.FloatField(required=False)
    radius_km = serializers.FloatField(required=False, min_value=0.1, max_value=200)
    category = serializers.SlugField(required=False)
    min_price = serializers.IntegerField(required=False, min_value=0)
    max_price = serializers.IntegerField(required=False, min_value=0)
    sort_by = serializers.ChoiceField(
        choices=["-created_at", "created_at", "-price", "price", "distance"],
        required=False,
        default="-created_at",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("sort_by") == "distance":
            if not attrs.get("lat") or not attrs.get("lon"):
                raise serializers.ValidationError(
                    "lat and lon are required when sort_by=distance."
                )
        if attrs.get("min_price") and attrs.get("max_price"):
            if attrs["min_price"] > attrs["max_price"]:
                raise serializers.ValidationError(
                    "min_price cannot be greater than max_price."
                )
        return attrs


class JobReviewSerializer(serializers.ModelSerializer):
    reviewer = UserPublicSerializer(read_only=True)

    class Meta:
        model = JobReview
        fields = ["id", "reviewer", "rating", "comment", "created_at"]
        read_only_fields = ["id", "reviewer", "created_at"]
