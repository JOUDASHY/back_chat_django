import uuid

from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .call_service import (
    broadcast_group_call_event,
    broadcast_group_call_message,
    finalize_group_call,
    join_group_call,
    reject_group_call,
    start_group_call,
)
from .livekit_utils import (
    create_livekit_token,
    get_livekit_config,
    livekit_is_configured,
)
from .models import GroupCall, GroupCallParticipant, Room
from .pusher_client import pusher_client
from .utils import get_user_display_name


def _user_call_payload(user, request):
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


class GroupCallStartView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not livekit_is_configured():
            return Response(
                {'error': 'Les appels ne sont pas configurés sur le serveur (LiveKit).'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        room_id = request.data.get('room_id')
        call_type = request.data.get('call_type', 'audio')

        if call_type not in ('audio', 'video'):
            return Response({'error': 'call_type doit être audio ou video.'}, status=400)

        try:
            room_id = int(room_id)
        except (TypeError, ValueError):
            return Response({'error': 'room_id invalide.'}, status=400)

        room = get_object_or_404(Room, pk=room_id)

        if not room.participants.filter(id=request.user.id).exists():
            return Response({'error': 'Vous n\'êtes pas membre de ce groupe.'}, status=403)

        other_users = room.participants.exclude(id=request.user.id)
        if not other_users.exists():
            return Response({'error': 'Aucun autre membre dans le groupe.'}, status=400)

        group_call = start_group_call(room=room, caller=request.user, call_type=call_type)
        cfg = get_livekit_config()

        caller_token = create_livekit_token(room_name=group_call.room_name, user=request.user)
        caller_info = _user_call_payload(request.user, request)

        participants_list = []
        for p in group_call.participants.select_related('user__profile').all():
            participants_list.append(_user_call_payload(p.user, request))

        payload = {
            'room_name': group_call.room_name,
            'call_type': call_type,
            'caller': caller_info,
            'livekit_url': cfg['url'],
            'room_id': room_id,
            'participants': participants_list,
        }

        broadcast_group_call_event(group_call, 'group-call-started', payload)

        return Response({
            'room_name': group_call.room_name,
            'call_type': call_type,
            'token': caller_token,
            'livekit_url': cfg['url'],
            'room_id': room_id,
            'participants': participants_list,
        })


class GroupCallRespondView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not livekit_is_configured():
            return Response({'error': 'LiveKit non configuré.'}, status=503)

        room_name = (request.data.get('room_name') or '').strip()
        action = (request.data.get('action') or '').strip().lower()

        if not room_name or action not in ('accept', 'reject'):
            return Response({'error': 'room_name et action (accept/reject) requis.'}, status=400)

        call = GroupCall.objects.filter(room_name=room_name).first()
        if not call:
            return Response({'error': 'Appel introuvable.'}, status=404)

        if action == 'reject':
            reject_group_call(room_name=room_name, user=request.user)
            payload = {
                'room_name': room_name,
                'user_id': request.user.id,
                'user': _user_call_payload(request.user, request),
            }
            broadcast_group_call_event(call, 'group-call-rejected', payload)
            return Response({'status': 'rejected'})

        join_group_call(room_name=room_name, user=request.user)
        cfg = get_livekit_config()
        token = create_livekit_token(room_name=room_name, user=request.user)
        user_info = _user_call_payload(request.user, request)

        payload = {
            'room_name': room_name,
            'user_id': request.user.id,
            'user': user_info,
        }
        broadcast_group_call_event(call, 'group-call-joined', payload)

        return Response({
            'room_name': room_name,
            'token': token,
            'livekit_url': cfg['url'],
            'user': user_info,
        })


class GroupCallEndView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        room_name = (request.data.get('room_name') or '').strip()

        if not room_name:
            return Response({'error': 'room_name requis.'}, status=400)

        call = finalize_group_call(room_name=room_name, ended_by=request.user)
        if call:
            broadcast_group_call_message(call, request)

        payload = {
            'room_name': room_name,
            'ended_by': request.user.id,
        }
        if call:
            broadcast_group_call_event(call, 'group-call-ended', payload)

        return Response({'status': 'ended'})


class GroupCallHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import timedelta
        from django.utils import timezone

        from .call_service import close_stale_ringing_calls

        for log in close_stale_ringing_calls():
            pass

        cutoff = timezone.now() - timedelta(seconds=45)
        stale_group_calls = GroupCall.objects.filter(
            status='ringing',
            started_at__lt=cutoff,
            message__isnull=True,
        )
        for call in stale_group_calls:
            finalize_group_call(room_name=call.room_name, ended_by=call.caller, status='missed')

        user = request.user
        calls = (
            GroupCall.objects.filter(
                participants__user=user
            ).exclude(
                status='ringing'
            ).select_related(
                'caller', 'caller__profile', 'room'
            ).distinct().order_by('-started_at')[:50]
        )

        data = []
        for call in calls:
            peer_count = call.participants.count() + 1
            direction = 'outgoing' if call.caller_id == user.id else 'incoming'
            call_event = {
                'type': call.call_type,
                'status': call.status,
                'duration_seconds': call.duration_seconds,
                'initiator_id': call.caller_id,
                'is_group': True,
            }
            from .call_service import format_call_event_preview
            data.append({
                'id': call.id,
                'room_name': call.room_name,
                'room_id': call.room_id,
                'call_type': call.call_type,
                'status': call.status,
                'direction': direction,
                'duration_seconds': call.duration_seconds,
                'started_at': call.started_at,
                'ended_at': call.ended_at,
                'preview': format_call_event_preview(call_event),
                'caller': _user_call_payload(call.caller, request),
                'participant_count': peer_count,
            })

        return Response(data)
