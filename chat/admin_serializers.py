from django.contrib.auth.models import User
from rest_framework import serializers

from .utils import get_user_display_name


class AdminUserSerializer(serializers.ModelSerializer):
    display_name = serializers.SerializerMethodField()
    is_online = serializers.BooleanField(read_only=True)
    account_status = serializers.SerializerMethodField()
    last_seen = serializers.SerializerMethodField()
    profile_image = serializers.SerializerMethodField()
    profile_status = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id',
            'username',
            'email',
            'first_name',
            'last_name',
            'display_name',
            'is_active',
            'is_staff',
            'is_superuser',
            'is_online',
            'account_status',
            'profile_status',
            'profile_image',
            'last_seen',
            'date_joined',
            'last_login',
        )

    def get_display_name(self, obj):
        return get_user_display_name(obj)

    def get_account_status(self, obj):
        return 'active' if obj.is_active else 'suspended'

    def get_last_seen(self, obj):
        if hasattr(obj, 'profile') and obj.profile.last_seen:
            return obj.profile.last_seen.isoformat()
        return None

    def get_profile_image(self, obj):
        request = self.context.get('request')
        if hasattr(obj, 'profile') and obj.profile.image and request:
            return request.build_absolute_uri(obj.profile.image.url)
        return None

    def get_profile_status(self, obj):
        if hasattr(obj, 'profile'):
            return obj.profile.status or 'offline'
        return 'offline'
