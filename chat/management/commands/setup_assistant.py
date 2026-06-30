import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from chat.models import Profile
from chat.utils import redis_client


class Command(BaseCommand):
    help = "Configure le user assistant (image de profil, statut en ligne)"

    def handle(self, *args, **options):
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
            self.stdout.write("User assistant cree")

        # Toujours en ligne
        try:
            redis_client.set(f"user:{user.id}:online", 1)
            self.stdout.write("Assistant marque en ligne (Redis)")
        except Exception:
            self.stdout.write("Redis indisponible, statut en ligne non defini")

        # Forcer l'image de profil
        avatar_url = "https://ui-avatars.com/api/?name=Assistant+IA&background=000b31&color=00d9ff&size=256&bold=true"
        try:
            resp = requests.get(avatar_url, timeout=10)
            if resp.status_code == 200:
                profile, _ = Profile.objects.get_or_create(user=user)
                profile.image.save(
                    f"assistant_avatar.png",
                    ContentFile(resp.content),
                    save=True,
                )
                self.stdout.write("Image de profil assistant definie")
            else:
                self.stdout.write(f"Echec telechargement avatar (HTTP {resp.status_code})")
        except Exception as e:
            self.stdout.write(f"Image non definie : {e}")

        self.stdout.write("Assistant pret !")
