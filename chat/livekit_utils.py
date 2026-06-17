import os

from django.conf import settings

from .utils import get_user_display_name


def get_livekit_config():
    return {
        'url': os.getenv('LIVEKIT_URL', getattr(settings, 'LIVEKIT_URL', '')),
        'api_key': os.getenv('LIVEKIT_API_KEY', getattr(settings, 'LIVEKIT_API_KEY', '')),
        'api_secret': os.getenv('LIVEKIT_API_SECRET', getattr(settings, 'LIVEKIT_API_SECRET', '')),
    }


def livekit_is_configured() -> bool:
    cfg = get_livekit_config()
    return bool(cfg['url'] and cfg['api_key'] and cfg['api_secret'])


def create_livekit_token(*, room_name: str, user) -> str:
    from livekit.api import AccessToken, VideoGrants

    cfg = get_livekit_config()
    if not livekit_is_configured():
        raise RuntimeError('LiveKit is not configured on the server.')

    identity = str(user.id)
    name = get_user_display_name(user)

    token = AccessToken(cfg['api_key'], cfg['api_secret'])
    token.with_identity(identity)
    token.with_name(name)
    token.with_grants(
        VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
        )
    )
    return token.to_jwt()


def build_call_room_name(caller_id: int, recipient_id: int, suffix: str) -> str:
    a, b = sorted([caller_id, recipient_id])
    return f'call-{a}-{b}-{suffix}'
