import redis
import pusher
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

try:
    redis_client = redis.StrictRedis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        decode_responses=True
    )
    redis_client.ping()
    redis_available = True
    logger.info("Connexion Redis établie avec succès")
except Exception as e:
    redis_client = None
    redis_available = False
    logger.error(f"Erreur de connexion Redis: {str(e)}")

# Configuration de Pusher
pusher_client = pusher.Pusher(
    app_id=settings.PUSHER_APP_ID,
    key=settings.PUSHER_KEY,
    secret=settings.PUSHER_SECRET,
    cluster=settings.PUSHER_CLUSTER,
    ssl=True
)

def update_online_status(user_id, is_online):
    """
    Met à jour le statut en ligne d'un utilisateur dans Redis
    """
    if redis_available:
        try:
            redis_client.set(f'user:{user_id}:online', 1 if is_online else 0)
            return True
        except Exception as e:
            logger.error(f"Erreur lors de la mise à jour du statut en ligne: {e}")
    return False

def get_online_status(user_id):
    """
    Récupère le statut en ligne d'un utilisateur depuis Redis
    """
    if redis_available:
        try:
            return bool(int(redis_client.get(f'user:{user_id}:online') or 0))
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du statut en ligne: {e}")
    return False


def get_user_display_name(user) -> str:
    """Nom affiché dans le chat : prénom + nom, sinon @username."""
    full = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full or user.username


def generate_unique_username(base: str) -> str:
    """Génère un username unique à partir d'une base (email, prénom, etc.)."""
    from django.contrib.auth.models import User

    normalized = ''.join(c for c in base.lower() if c.isalnum() or c in '._')[:30]
    if not normalized:
        normalized = 'user'

    username = normalized
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f"{normalized}{counter}"
        counter += 1
    return username


def resolve_user_by_login_identifier(identifier: str):
    """Retrouve un utilisateur par email ou identifiant (@username)."""
    from django.contrib.auth.models import User
    from django.db.models import Q

    identifier = (identifier or '').strip()
    if not identifier:
        return None
    return User.objects.filter(
        Q(username__iexact=identifier) | Q(email__iexact=identifier)
    ).first()
