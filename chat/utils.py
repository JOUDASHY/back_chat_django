import redis
import pusher
from django.conf import settings

# Tentative de connexion à Redis, avec gestion d'erreur
try:
    redis_client = redis.StrictRedis(host='localhost', port=6379, db=0)
    redis_available = True
except redis.exceptions.ConnectionError:
    redis_client = None
    redis_available = False
    print("Avertissement: Redis n'est pas disponible. Les fonctionnalités de statut en ligne sont désactivées.")

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
