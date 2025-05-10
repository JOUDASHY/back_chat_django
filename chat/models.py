from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()
# chat/models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class Profile(models.Model):
    GENDER_CHOICES = (
        ('M', 'Masculin'),
        ('F', 'Féminin'),
        ('O', 'Autre'),
    )
    
    STATUS_CHOICES = (
        ('online', 'En ligne'),
        ('offline', 'Hors ligne'),
        ('away', 'Absent'),
        ('busy', 'Occupé'),
        ('invisible', 'Invisible'),
    )
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    image = models.ImageField(upload_to='avatars/', default='avatars/user.jpg', null=True, blank=True)
    cover_image = models.ImageField(upload_to='covers/', default='covers/default.jpg', null=True, blank=True)
    bio = models.TextField(max_length=500, null=True, blank=True)
    lieu = models.CharField(max_length=255, null=True, blank=True)
    date_naiv = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES, null=True, blank=True)
    phone_number = models.CharField(max_length=20, null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='offline', null=True, blank=True)
    passion = models.TextField(null=True, blank=True)
    profession = models.CharField(max_length=100, null=True, blank=True)
    website = models.URLField(max_length=200, null=True, blank=True)
    social_links = models.JSONField(null=True, blank=True, default=dict)
    last_seen = models.DateTimeField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    theme_preference = models.CharField(max_length=20, default='light', null=True, blank=True)
    language_preference = models.CharField(max_length=10, default='fr', null=True, blank=True)
    notification_preferences = models.JSONField(null=True, blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Profil de {self.user.username}"
    
    def age(self):
        from datetime import date
        if self.date_naiv:
            today = date.today()
            return today.year - self.date_naiv.year - ((today.month, today.day) < (self.date_naiv.month, self.date_naiv.day))
        return None



# Créer automatiquement un Profile à la création d’un User

@receiver(post_save, sender=User)
def create_or_update_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
    else:
        instance.profile.save()




class Room(models.Model):
    name = models.CharField(max_length=100)
    participants = models.ManyToManyField(
        User,
        related_name="chat_rooms",
        blank=True
    )

    def __str__(self):
        return self.name
class Message(models.Model):
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_messages'
    )
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_messages',
        null=True,
        blank=True
    )
    room = models.ForeignKey(
        'Room',  # Assuming Room is defined elsewhere in your models
        on_delete=models.CASCADE,
        related_name='messages',
        null=True,
        blank=True
    )
    content = models.TextField()
    attachment = models.FileField(upload_to='message_attachments/', null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        attachment_info = f" with attachment" if self.attachment else ""
        if self.room:
            return f"[{self.room.name}] {self.sender.username}: {self.content[:20]}{attachment_info}"
        if self.recipient:
            return f"[PM] {self.sender.username} → {self.recipient.username}: {self.content[:20]}{attachment_info}"
        return f"{self.sender.username}: {self.content[:20]}{attachment_info}"