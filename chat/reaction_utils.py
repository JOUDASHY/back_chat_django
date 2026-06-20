from .models import Message, MessageReaction
from .utils import get_user_display_name

ALLOWED_REACTION_EMOJIS = frozenset({'👍', '❤️', '😂', '😮', '😢', '🙏', '👏', '🔥'})


def user_can_react_to_message(message: Message, user) -> bool:
    if message.call_event:
        return False
    if message.room_id:
        return message.room.participants.filter(id=user.id).exists()
    if message.recipient_id:
        return user.id in (message.sender_id, message.recipient_id)
    return False


def serialize_message_reactions(message: Message, current_user) -> list[dict]:
    grouped: dict[str, dict] = {}

    for reaction in message.reactions.select_related('user').all():
        bucket = grouped.get(reaction.emoji)
        if not bucket:
            bucket = {
                'emoji': reaction.emoji,
                'count': 0,
                'users': [],
                'reacted_by_me': False,
            }
            grouped[reaction.emoji] = bucket

        bucket['count'] += 1
        bucket['users'].append({
            'id': reaction.user_id,
            'username': reaction.user.username,
            'display_name': get_user_display_name(reaction.user),
        })
        if reaction.user_id == current_user.id:
            bucket['reacted_by_me'] = True

    return list(grouped.values())


def toggle_message_reaction(*, message: Message, user, emoji: str) -> list[dict]:
    if emoji not in ALLOWED_REACTION_EMOJIS:
        raise ValueError('invalid emoji')

    existing = MessageReaction.objects.filter(message=message, user=user).first()
    if existing:
        if existing.emoji == emoji:
            existing.delete()
        else:
            existing.emoji = emoji
            existing.save(update_fields=['emoji'])
    else:
        MessageReaction.objects.create(message=message, user=user, emoji=emoji)

    return serialize_message_reactions(message, user)
