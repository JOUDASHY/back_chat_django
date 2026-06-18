from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import filters, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .admin_serializers import AdminUserSerializer
from .permissions import IsStaffUser
from .pusher_client import pusher_client
from .utils import get_online_status, update_online_status


def _enrich_online(user: User) -> User:
    user.is_online = get_online_status(user.id)
    return user


def _force_offline(user: User) -> None:
    if hasattr(user, 'profile'):
        user.profile.status = 'offline'
        user.profile.save(update_fields=['status'])
    update_online_status(user.id, False)
    pusher_client.trigger(
        'presence-channel',
        'user-status-changed',
        {'userId': user.id, 'isOnline': False},
    )
    pusher_client.trigger(f'user-{user.id}-calls', 'account-suspended', {})
    pusher_client.trigger(f'user-{user.id}-conversations', 'account-suspended', {})


class AdminUserListView(generics.ListAPIView):
    """Liste complète des utilisateurs pour le back-office."""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAuthenticated, IsStaffUser]
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'email', 'first_name', 'last_name']

    def get_queryset(self):
        qs = User.objects.all().select_related('profile').order_by('-date_joined')
        is_active = self.request.query_params.get('is_active')
        if is_active in ('true', '1'):
            qs = qs.filter(is_active=True)
        elif is_active in ('false', '0'):
            qs = qs.filter(is_active=False)
        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        users = [_enrich_online(u) for u in queryset]

        online = request.query_params.get('online')
        if online in ('true', '1'):
            users = [u for u in users if u.is_online]
        elif online in ('false', '0'):
            users = [u for u in users if not u.is_online]

        serializer = self.get_serializer(users, many=True)
        return Response({
            'count': len(users),
            'results': serializer.data,
        })


class AdminSuspendUserView(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    def post(self, request, pk):
        if request.user.id == pk:
            return Response(
                {'error': 'Vous ne pouvez pas suspendre votre propre compte.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target = get_object_or_404(User.objects.select_related('profile'), pk=pk)

        if target.is_superuser and not request.user.is_superuser:
            return Response(
                {'error': 'Seul un super-admin peut suspendre ce compte.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not target.is_active:
            return Response(
                {'detail': 'Compte déjà suspendu.', 'user': AdminUserSerializer(target, context={'request': request}).data},
                status=status.HTTP_200_OK,
            )

        target.is_active = False
        target.save(update_fields=['is_active'])
        _force_offline(target)

        target.is_online = False
        return Response({
            'detail': 'Compte suspendu.',
            'user': AdminUserSerializer(target, context={'request': request}).data,
        })


class AdminUnsuspendUserView(APIView):
    permission_classes = [IsAuthenticated, IsStaffUser]

    def post(self, request, pk):
        target = get_object_or_404(User.objects.select_related('profile'), pk=pk)

        if target.is_active:
            target.is_online = get_online_status(target.id)
            return Response(
                {
                    'detail': 'Compte déjà actif.',
                    'user': AdminUserSerializer(target, context={'request': request}).data,
                },
                status=status.HTTP_200_OK,
            )

        target.is_active = True
        target.save(update_fields=['is_active'])
        target.is_online = get_online_status(target.id)

        return Response({
            'detail': 'Compte réactivé.',
            'user': AdminUserSerializer(target, context={'request': request}).data,
        })
