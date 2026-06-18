from rest_framework.permissions import BasePermission


class IsStaffUser(BasePermission):
    """Accès réservé aux comptes staff (admin)."""

    message = 'Accès administrateur requis.'

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_staff
        )
