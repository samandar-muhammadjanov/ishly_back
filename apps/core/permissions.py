"""
Custom DRF permissions.
Role-based access control for Employer and Worker roles.
"""

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class IsEmployer(BasePermission):
    """
    Allows access only to users with Employer role.
    """

    message = "Only employers can perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "employer"
        )


class IsWorker(BasePermission):
    """
    Allows access only to users with Worker role.
    """

    message = "Only workers can perform this action."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == "worker"
        )


class IsEmployerOrWorker(BasePermission):
    """
    Allows access to both Employer and Worker roles (any authenticated user).
    """

    message = "Authentication required."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return bool(request.user and request.user.is_authenticated)


class IsOwnerOrAdmin(BasePermission):
    """
    Object-level permission: only the owner of an object or an admin can access it.
    The model must have an attribute pointing to the request user.
    """

    message = "You do not have permission to access this resource."

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        if request.user.is_staff:
            return True
        # Check ownership via 'user' or 'employer' or 'worker' attribute
        for attr in ("user", "employer", "worker", "created_by"):
            owner = getattr(obj, attr, None)
            if owner is not None and owner == request.user:
                return True
        return False


class IsJobEmployer(BasePermission):
    """
    Allows access only to the employer who created the job.
    """

    message = "Only the job's employer can perform this action."

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        return obj.employer == request.user


class IsJobWorker(BasePermission):
    """
    Allows access only to the worker assigned to the job.
    """

    message = "Only the assigned worker can perform this action."

    def has_object_permission(self, request: Request, view: APIView, obj) -> bool:
        return obj.worker == request.user


class IsActiveUser(BasePermission):
    """
    Ensures the user account is active and not blocked.
    """

    message = "Your account has been suspended."

    def has_permission(self, request: Request, view: APIView) -> bool:
        return (
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and not getattr(request.user, "is_blocked", False)
        )
