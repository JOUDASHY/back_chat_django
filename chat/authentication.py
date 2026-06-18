from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication


class ActiveJWTAuthentication(JWTAuthentication):
    """Refuse les JWT des comptes suspendus (is_active=False)."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not user.is_active:
            raise AuthenticationFailed(
                'Ce compte est suspendu. Contactez un administrateur.',
                code='account_suspended',
            )
        return user
