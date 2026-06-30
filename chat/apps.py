from django.apps import AppConfig
from django.db.models.signals import post_migrate


def create_assistant_user(sender, **kwargs):
    from django.contrib.auth.models import User
    from chat.utils import redis_client

    user, created = User.objects.get_or_create(
        username="assistant",
        defaults={
            "email": "ai@chat.local",
            "first_name": "Assistant",
            "last_name": "IA",
        },
    )
    if created:
        user.set_password("assistant_ai_secret")
        user.save()

    # Marquer en ligne dans Redis
    try:
        redis_client.set(f"user:{user.id}:online", 1)
    except Exception:
        pass


class ChatConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'chat'

    def ready(self):
        post_migrate.connect(create_assistant_user, sender=self)
