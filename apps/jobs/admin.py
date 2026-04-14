"""Jobs admin configuration."""

from django.contrib import admin
from django.core.cache import cache
from django.utils.html import format_html

from .models import Job, JobCategory, JobImage, JobReview, JobStatus

_CATEGORIES_CACHE_KEY = "job_categories"


@admin.register(JobCategory)
class JobCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "icon_preview", "is_active", "sort_order"]
    list_editable = ["is_active", "sort_order"]
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ["name"]
    readonly_fields = ["icon_preview"]

    def icon_preview(self, obj):
        if not obj.icon:
            return "-"
        url = obj.icon.url
        return format_html('<img src="{}" width="32" height="32" style="object-fit:contain" />', url)
    icon_preview.short_description = "Icon"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        cache.delete(_CATEGORIES_CACHE_KEY)

    def delete_model(self, request, obj):
        super().delete_model(request, obj)
        cache.delete(_CATEGORIES_CACHE_KEY)

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset)
        cache.delete(_CATEGORIES_CACHE_KEY)


class JobImageInline(admin.TabularInline):
    model = JobImage
    extra = 0
    readonly_fields = ["id"]


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = [
        "title", "status_badge", "employer", "worker",
        "price_display", "category", "created_at",
    ]
    list_filter = ["status", "category", "created_at"]
    search_fields = ["title", "employer__phone_number", "worker__phone_number"]
    readonly_fields = [
        "id", "created_at", "updated_at",
        "accepted_at", "started_at", "completed_at", "cancelled_at",
    ]
    raw_id_fields = ["employer", "worker"]
    inlines = [JobImageInline]
    ordering = ["-created_at"]

    fieldsets = (
        ("Job Info", {"fields": ("id", "title", "description", "category", "price")}),
        ("Location", {"fields": ("latitude", "longitude", "address")}),
        ("Parties", {"fields": ("employer", "worker")}),
        ("Status", {"fields": ("status", "cancel_reason", "scheduled_time")}),
        ("Timestamps", {
            "fields": ("created_at", "updated_at", "accepted_at", "started_at", "completed_at", "cancelled_at"),
            "classes": ("collapse",),
        }),
    )

    def price_display(self, obj: Job) -> str:
        return f"{obj.price_uzs:,.0f} UZS"
    price_display.short_description = "Price"

    def status_badge(self, obj: Job) -> str:
        colors = {
            JobStatus.CREATED: "#17a2b8",
            JobStatus.ACCEPTED: "#ffc107",
            JobStatus.IN_PROGRESS: "#007bff",
            JobStatus.COMPLETED: "#28a745",
            JobStatus.CANCELLED: "#dc3545",
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background:{};color:white;padding:2px 8px;border-radius:4px">{}</span>',
            color,
            obj.get_status_display(),
        )
    status_badge.short_description = "Status"


@admin.register(JobReview)
class JobReviewAdmin(admin.ModelAdmin):
    list_display = ["job", "reviewer", "reviewee", "rating", "created_at"]
    list_filter = ["rating", "created_at"]
    raw_id_fields = ["job", "reviewer", "reviewee"]
    readonly_fields = ["id", "created_at"]
