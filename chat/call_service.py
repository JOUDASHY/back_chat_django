from django.utils import timezone

from .models import CallLog, Message
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
    return message.content or ''


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
