from datetime import timedelta

from django.utils import timezone

from .models import CallLog, GroupCall, GroupCallParticipant, Message, Room
from .pusher_client import pusher_client
from .serializers import MessageSerializer
from .utils import get_user_display_name


def format_call_preview(call_event: dict) -> str:
    call_type = call_event.get('type', 'audio')
    status = call_event.get('status', 'completed')
    duration = int(call_event.get('duration_seconds') or 0)
    label = 'Appel vidéo' if call_type == 'video' else 'Appel vocal'

    if status == 'completed':
        if duration >= 60:
            mins = duration // 60
            secs = duration % 60
            return f'{label} · {mins} min {secs:02d} s' if secs else f'{label} · {mins} min'
        if duration > 0:
            return f'{label} · {duration} s'
        return label

    labels = {
        'missed': f'{label} manqué',
        'rejected': f'{label} refusé',
        'cancelled': f'{label} annulé',
    }
    return labels.get(status, label)


def message_preview(message) -> str:
    """Texte affiché dans la sidebar pour un message (y compris appels)."""
    if getattr(message, 'call_event', None):
        return format_call_preview(message.call_event)
    
    content = message.content or ''
    attachment = getattr(message, 'attachment', None)
    
    if attachment and not content:
        filename = getattr(attachment, 'name', '') or ''
        filename = filename.lower()
        if filename.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.heic')):
            return '📷 Photo'
        elif filename.endswith(('.mp4', '.mov', '.avi', '.mkv')):
            return '🎥 Vidéo'
        elif filename.endswith(('.mp3', '.wav', '.ogg', '.m4a', '.webm')):
            basename = filename.split('/')[-1].split('\\')[-1]
            if basename.startswith('voice_'):
                return '🎤 Message vocal'
            return '🎵 Audio'
        elif filename.endswith(('.pdf')):
            return '📄 Fichier PDF'
        else:
            return '📎 Fichier joint'
        
    return content


def start_call_log(*, room_name: str, caller, recipient, call_type: str) -> CallLog:
    return CallLog.objects.create(
        room_name=room_name,
        caller=caller,
        recipient=recipient,
        call_type=call_type,
        status='ringing',
    )


def accept_call_log(room_name: str) -> CallLog | None:
    log = CallLog.objects.filter(room_name=room_name, status='ringing').first()
    if not log:
        return None
    log.answered_at = timezone.now()
    log.save(update_fields=['answered_at'])
    return log


def _resolve_final_status(log: CallLog, ended_by) -> str:
    if log.status in ('rejected', 'missed', 'cancelled', 'completed'):
        return log.status
    if log.answered_at:
        return 'completed'
    if ended_by and ended_by.id == log.caller_id:
        return 'missed'
    return 'cancelled'


def finalize_call_log(*, room_name: str, ended_by, status: str | None = None) -> CallLog | None:
    log = CallLog.objects.filter(room_name=room_name).exclude(
        status__in=('completed', 'missed', 'rejected', 'cancelled')
    ).first()
    if not log:
        log = CallLog.objects.filter(room_name=room_name).first()
    if not log or log.message_id:
        return log

    final_status = status or _resolve_final_status(log, ended_by)
    now = timezone.now()
    duration = 0

    if final_status == 'completed' and log.answered_at:
        duration = max(0, int((now - log.answered_at).total_seconds()))

    log.status = final_status
    log.ended_at = now
    log.ended_by = ended_by
    log.duration_seconds = duration
    log.save()

    msg = Message.objects.create(
        sender=log.caller,
        recipient=log.recipient,
        content='',
        call_event={
            'type': log.call_type,
            'status': final_status,
            'duration_seconds': duration,
            'initiator_id': log.caller_id,
        },
    )
    log.message = msg
    log.save(update_fields=['message'])

    return log


def reject_call_log(*, room_name: str, ended_by) -> CallLog | None:
    log = CallLog.objects.filter(room_name=room_name, status='ringing').first()
    if not log or log.message_id:
        return log

    log.status = 'rejected'
    log.ended_at = timezone.now()
    log.ended_by = ended_by
    log.save()

    msg = Message.objects.create(
        sender=log.caller,
        recipient=log.recipient,
        content='',
        call_event={
            'type': log.call_type,
            'status': 'rejected',
            'duration_seconds': 0,
            'initiator_id': log.caller_id,
        },
    )
    log.message = msg
    log.save(update_fields=['message'])
    return log


def close_stale_ringing_calls(*, max_age_seconds: int = 45) -> list[CallLog]:
    """Clôture les appels jamais décrochés, restés en sonnerie."""
    cutoff = timezone.now() - timedelta(seconds=max_age_seconds)
    logs = list(
        CallLog.objects.filter(
            status='ringing',
            started_at__lt=cutoff,
            message__isnull=True,
            answered_at__isnull=True,
        ).select_related('caller', 'recipient')
    )
    finalized = []
    for log in logs:
        result = finalize_call_log(room_name=log.room_name, ended_by=log.caller)
        if result:
            finalized.append(result)
    return finalized


def broadcast_call_message(log: CallLog, request) -> None:
    if not log or not log.message:
        return

    msg = log.message
    message_data = MessageSerializer(msg, context={'request': request}).data
    a, b = sorted([msg.sender_id, msg.recipient_id])
    pusher_client.trigger(f'private-chat-{a}-{b}', 'new-message', message_data)

    preview = format_call_preview(msg.call_event or {})
    conversation_id = int(f'{a}{b}')
    ts = msg.timestamp.isoformat()

    for user_id, is_recipient in ((log.caller_id, False), (log.recipient_id, True)):
        pusher_client.trigger(
            f'user-{user_id}-conversations',
            'new-message',
            {
                'conversation': {
                    'id': conversation_id,
                    'lastMessage': preview,
                    'timestamp': ts,
                    'incrementUnread': is_recipient,
                    'lastMessageSeen': not is_recipient,
                    'lastMessageSenderId': log.caller_id,
                    'lastMessageIsRead': False,
                }
            },
        )


def start_group_call(*, room: Room, caller, call_type: str) -> GroupCall:
    import uuid
    suffix = uuid.uuid4().hex[:10]
    room_name = f'group-call-{room.id}-{suffix}'

    group_call = GroupCall.objects.create(
        room_name=room_name,
        caller=caller,
        room=room,
        call_type=call_type,
        status='ringing',
    )

    participants = room.participants.exclude(id=caller.id)
    participants_list = []
    for user in participants:
        participant = GroupCallParticipant.objects.create(
            call=group_call,
            user=user,
            status='ringing',
        )
        participants_list.append(participant)

    return group_call


def join_group_call(room_name: str, user) -> GroupCallParticipant | None:
    participant = GroupCallParticipant.objects.filter(
        call__room_name=room_name, user=user, status='ringing'
    ).first()
    if not participant:
        return None
    participant.status = 'joined'
    participant.joined_at = timezone.now()
    participant.save(update_fields=['status', 'joined_at'])

    call = participant.call
    if call.status == 'ringing':
        call.status = 'active'
        call.answered_at = timezone.now()
        call.save(update_fields=['status', 'answered_at'])

    return participant


def reject_group_call(room_name: str, user) -> GroupCallParticipant | None:
    participant = GroupCallParticipant.objects.filter(
        call__room_name=room_name, user=user, status='ringing'
    ).first()
    if not participant:
        return None
    participant.status = 'rejected'
    participant.rejected_at = timezone.now()
    participant.save(update_fields=['status', 'rejected_at'])
    return participant


def finalize_group_call(*, room_name: str, ended_by, status: str | None = None) -> GroupCall | None:
    call = GroupCall.objects.filter(room_name=room_name).exclude(
        status__in=('completed', 'missed', 'cancelled')
    ).first()
    if not call:
        call = GroupCall.objects.filter(room_name=room_name).first()
    if not call or call.message_id:
        return call

    now = timezone.now()

    if status:
        final_status = status
    elif call.answered_at:
        final_status = 'completed'
    elif ended_by and ended_by.id == call.caller_id:
        final_status = 'cancelled'
    else:
        final_status = 'completed'

    duration = 0
    if final_status == 'completed' and call.answered_at:
        duration = max(0, int((now - call.answered_at).total_seconds()))

    call.status = final_status
    call.ended_at = now
    call.ended_by = ended_by
    call.duration_seconds = duration
    call.save()

    # Create history message in group chat
    sender_name = get_user_display_name(call.caller)
    label = 'Appel vidéo' if call.call_type == 'video' else 'Appel vocal'
    participant_names = [get_user_display_name(p.user) for p in call.participants.select_related('user')]
    content = f"{label} de groupe ({len(participant_names) + 1} participants)"

    msg = Message.objects.create(
        sender=call.caller,
        room=call.room,
        content=content,
        call_event={
            'type': call.call_type,
            'status': final_status,
            'duration_seconds': duration,
            'initiator_id': call.caller_id,
            'is_group': True,
        },
    )
    call.message = msg
    call.save(update_fields=['message'])

    return call


def broadcast_group_call_event(call: GroupCall, event: str, payload: dict) -> None:
    if not call.room:
        return
    pusher_client.trigger(f'group-chat-{call.room.id}', event, payload)

    for participant in call.participants.select_related('user'):
        pusher_client.trigger(f'user-{participant.user.id}-calls', event, payload)

    pusher_client.trigger(f'user-{call.caller.id}-calls', event, payload)


def broadcast_group_call_message(call: GroupCall, request) -> None:
    if not call or not call.message:
        return
    msg = call.message
    message_data = MessageSerializer(msg, context={'request': request}).data
    if call.room:
        pusher_client.trigger(f'group-chat-{call.room.id}', 'new-message', message_data)

    preview = format_call_event_preview(msg.call_event or {})
    ts = msg.timestamp.isoformat()
    room_id = call.room_id

    # Notify all participants
    all_ids = set([call.caller_id])
    for p in call.participants.all():
        all_ids.add(p.user_id)

    for user_id in all_ids:
        is_sender = user_id == call.caller_id
        pusher_client.trigger(
            f'user-{user_id}-conversations',
            'new-message',
            {
                'conversation': {
                    'id': room_id,
                    'lastMessage': preview,
                    'timestamp': ts,
                    'incrementUnread': not is_sender,
                    'lastMessageSeen': is_sender,
                    'lastMessageSenderId': call.caller_id,
                    'lastMessageIsRead': False,
                    'isGroup': True,
                }
            },
        )


def format_call_event_preview(call_event: dict) -> str:
    call_type = call_event.get('type', 'audio')
    status = call_event.get('status', 'completed')
    duration = int(call_event.get('duration_seconds') or 0)
    is_group = call_event.get('is_group', False)
    label = 'Appel vidéo' if call_type == 'video' else 'Appel vocal'
    if is_group:
        label += ' de groupe'

    if status == 'completed':
        if duration >= 60:
            mins = duration // 60
            secs = duration % 60
            return f'{label} · {mins} min {secs:02d} s' if secs else f'{label} · {mins} min'
        if duration > 0:
            return f'{label} · {duration} s'
        return label

    labels = {
        'missed': f'{label} manqué',
        'rejected': f'{label} refusé',
        'cancelled': f'{label} annulé',
    }
    return labels.get(status, label)
