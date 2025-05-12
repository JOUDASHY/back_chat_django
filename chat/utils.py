import redis
import pusher
import logging
from django.conf import settings
from redis.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, AuthenticationError, ResponseError

logger = logging.getLogger(__name__)

# Tentative de connexion à Redis, avec gestion d'erreur
retry = Retry(ExponentialBackoff(), 3)
try:
    logger.debug(f"Tentative de connexion à Redis: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    redis_client = redis.StrictRedis(
        host=settings.REDIS_HOST,
        port=settings.REDIS_PORT,
        db=settings.REDIS_DB,
        password=settings.REDIS_PASSWORD,
        decode_responses=True,
        retry=retry,
        socket_timeout=5,
        socket_connect_timeout=5
    )
    # Test the connection
    redis_client.ping()
    redis_available = True
    logger.info("Connexion Redis établie avec succès")
except (ConnectionError, AuthenticationError, ResponseError) as e:
    redis_client = None
    redis_available = False
    logger.error(f"Erreur de connexion Redis: {str(e)}")
    logger.debug(f"Détails de configuration Redis: host={settings.REDIS_HOST}, port={settings.REDIS_PORT}, password={'*' * len(settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else '')}")

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
            print(f"Erreur lors de la mise à jour du statut en ligne: {e}")
    return False

def get_online_status(user_id):
    """
    Récupère le statut en ligne d'un utilisateur depuis Redis
    """
    if redis_available:
        try:
            return bool(int(redis_client.get(f'user:{user_id}:online') or 0))
        except Exception as e:
            print(f"Erreur lors de la récupération du statut en ligne: {e}")
    return False
