import uuid

from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .livekit_utils import (
    build_call_room_name,
    create_livekit_token,
    get_livekit_config,
    livekit_is_configured,
)
from .pusher_client import pusher_client
from .utils import get_user_display_name


def _caller_payload(user, request):
    image = None
    try:
        if user.profile.image:
            image = request.build_absolute_uri(user.profile.image.url)
    except Exception:
        pass
    return {
        'id': user.id,
        'username': user.username,
        'display_name': get_user_display_name(user),
        'image': image,
    }


def _notify_user(user_id: int, event: str, payload: dict):
    pusher_client.trigger(f'user-{user_id}-calls', event, payload)


class CallStartView(APIView):
    """Démarrer un appel audio ou vidéo 1-à-1."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not livekit_is_configured():
            return Response(
                {'error': 'Les appels ne sont pas configurés sur le serveur (LiveKit).'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        recipient_id = request.data.get('recipient_id')
        call_type = request.data.get('call_type', 'audio')

        if call_type not in ('audio', 'video'):
            return Response({'error': 'call_type doit être audio ou video.'}, status=400)

        try:
            recipient_id = int(recipient_id)
        except (TypeError, ValueError):
            return Response({'error': 'recipient_id invalide.'}, status=400)

        if recipient_id == request.user.id:
            return Response({'error': 'Impossible de vous appeler vous-même.'}, status=400)

        recipient = get_object_or_404(User, pk=recipient_id)
        suffix = uuid.uuid4().hex[:10]
        room_name = build_call_room_name(request.user.id, recipient_id, suffix)
        cfg = get_livekit_config()

        caller_token = create_livekit_token(room_name=room_name, user=request.user)
        caller_info = _caller_payload(request.user, request)

        _notify_user(
            recipient_id,
            'incoming-call',
            {
                'room_name': room_name,
                'call_type': call_type,
                'caller': caller_info,
                'livekit_url': cfg['url'],
            },
        )

        return Response({
            'room_name': room_name,
            'call_type': call_type,
            'token': caller_token,
            'livekit_url': cfg['url'],
            'recipient': {
                'id': recipient.id,
                'display_name': get_user_display_name(recipient),
            },
        })


class CallRespondView(APIView):
    """Accepter ou refuser un appel entrant."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not livekit_is_configured():
            return Response({'error': 'LiveKit non configuré.'}, status=503)

        room_name = (request.data.get('room_name') or '').strip()
        action = (request.data.get('action') or '').strip().lower()
        caller_id = request.data.get('caller_id')

        if not room_name or action not in ('accept', 'reject'):
            return Response({'error': 'room_name et action (accept/reject) requis.'}, status=400)

        try:
            caller_id = int(caller_id)
        except (TypeError, ValueError):
            return Response({'error': 'caller_id invalide.'}, status=400)

        if action == 'reject':
            _notify_user(caller_id, 'call-rejected', {'room_name': room_name})
            return Response({'status': 'rejected'})

        cfg = get_livekit_config()
        token = create_livekit_token(room_name=room_name, user=request.user)

        _notify_user(
            caller_id,
            'call-accepted',
            {
                'room_name': room_name,
                'user': _caller_payload(request.user, request),
            },
        )

        return Response({
            'room_name': room_name,
            'token': token,
            'livekit_url': cfg['url'],
        })


class CallEndView(APIView):
    """Terminer un appel en cours."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        room_name = (request.data.get('room_name') or '').strip()
        peer_id = request.data.get('peer_id')

        if not room_name:
            return Response({'error': 'room_name requis.'}, status=400)

        try:
            peer_id = int(peer_id)
        except (TypeError, ValueError):
            return Response({'error': 'peer_id invalide.'}, status=400)

        _notify_user(
            peer_id,
            'call-ended',
            {
                'room_name': room_name,
                'ended_by': request.user.id,
            },
        )

        return Response({'status': 'ended'})
