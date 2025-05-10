# chat/serializers.py

from rest_framework import serializers
from .models import Message
from django.contrib.auth import get_user_model
# from django.contrib.auth.models import User
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.models import User
# from rest_framework import serializers
from .models import Profile
# serializers.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
# Dans chat/serializers.py



# serializers.py
# serializers.py
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Passe le contexte de la requête au UserSerializer
        user_serializer = UserSerializer(
            instance=self.user,
            context={'request': self.context.get('request')}  # 🚨 Nécessaire pour l'URL
        )
        data['user'] = user_serializer.data
        return data
# serializers.py
# serializers.py
# serializers.py
class ProfileSerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    cover_image = serializers.SerializerMethodField()
    age = serializers.IntegerField(read_only=True)

    class Meta:
        model = Profile
        fields = (
            'image', 'cover_image', 'bio', 'lieu', 'date_naiv', 'gender',
            'phone_number', 'status', 'passion', 'profession', 'website',
            'social_links', 'last_seen', 'is_verified', 'theme_preference',
            'language_preference', 'notification_preferences', 'age',
            'created_at', 'updated_at'
        )

    def get_image(self, obj):
        if obj.image:
            return self.context['request'].build_absolute_uri(obj.image.url)
        return None
        
    def get_cover_image(self, obj):
        if obj.cover_image:
            return self.context['request'].build_absolute_uri(obj.cover_image.url)
        return None
        


from .models import Message, Room

User = get_user_model()
# from rest_framework import serializers
# from django.contrib.auth import get_user_model
from .models import Room

# User = get_user_model()
# from django.contrib.auth.models import User
# from rest_framework import serializers

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    is_online = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name',
            'profile', 'is_online'
        )

from rest_framework import serializers

class ConversationCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=True)

class ConversationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    lastMessage = serializers.CharField()
    timestamp = serializers.DateTimeField()
    isGroup = serializers.BooleanField()
    userId = serializers.IntegerField(required=False)  # Ajoutez cette ligne

class MessageSerializer(serializers.ModelSerializer):
    sender = serializers.StringRelatedField(read_only=True)
    recipient = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False, allow_null=True
    )
    room = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(),
        required=False, allow_null=True
    )
    attachment = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = Message
        fields = ["id", "sender", "recipient", "room", "content", "timestamp", "attachment"]
        read_only_fields = ["id", "sender", "timestamp"]

        
             
class RoomSerializer(serializers.ModelSerializer):
    participants = serializers.PrimaryKeyRelatedField(
        many=True, queryset=User.objects.all()
    )

    class Meta:
        model = Room
        fields = ["id", "name", "participants"]

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    gender = serializers.CharField(write_only=True, required=False)  # Champ pour le sexe

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'gender', 'first_name', 'last_name')
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': False}
        }

    def create(self, validated_data):
        # Extraire gender avant de créer l'utilisateur
        gender = validated_data.pop('gender', None)
        
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data.get('email', ''),
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        
        # Mettre à jour le profil avec le sexe si fourni
        if gender:
            profile = user.profile
            profile.gender = gender
            profile.save()
            
        return user
        
class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Aucun utilisateur avec cet email.")
        return value

    def save(self):
        email = self.validated_data['email']
        user = User.objects.get(email=email)
        token_generator = PasswordResetTokenGenerator()
        token = token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # Configuration du lien de réinitialisation
        reset_link = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}/"
        
        # Rendu du template email
        context = {
            'user': user,
            'reset_link': reset_link,
        }
        email_body = render_to_string('email/password_reset.html', context)
        
        # Envoi de l'email
        send_mail(
            subject="Réinitialisation de votre mot de passe",
            message="",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            html_message=email_body,
            fail_silently=False,
        )

class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        try:
            uid = force_str(urlsafe_base64_decode(attrs['uid']))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            raise serializers.ValidationError({"uid": "Identifiant invalide"})

        if not PasswordResetTokenGenerator().check_token(user, attrs['token']):
            raise serializers.ValidationError({"token": "Token invalide ou expiré"})

        attrs['user'] = user
        return attrs

    def save(self):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save()


# Ajoutez ce nouveau serializer
class RecipientProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = ['image', 'lieu', 'date_naiv', 'status', 'passion']

# Modifiez le MessageSerializer existant

# Dans chat/serializers.py

class ProfileUpdateSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(required=False, allow_null=True)
    cover_image = serializers.ImageField(required=False, allow_null=True)
    social_links = serializers.JSONField(required=False)
    notification_preferences = serializers.JSONField(required=False)

    class Meta:
        model = Profile
        fields = [
            'image', 'cover_image', 'bio', 'lieu', 'date_naiv', 'gender',
            'phone_number', 'status', 'passion', 'profession', 'website',
            'social_links', 'theme_preference', 'language_preference',
            'notification_preferences'
        ]

class UserUpdateSerializer(serializers.ModelSerializer):
    profile = ProfileUpdateSerializer()

    class Meta:
        model = User
        fields = ['username', 'email', 'first_name', 'last_name', 'profile']
        extra_kwargs = {
            'username': {'required': False},
            'email': {'required': False}
        }

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        profile = instance.profile

        # Mise à jour de l'utilisateur
        instance.username = validated_data.get('username', instance.username)
        instance.email = validated_data.get('email', instance.email)
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.save()

        # Mise à jour du profil
        for attr, value in profile_data.items():
            setattr(profile, attr, value)
        profile.save()

        # Add the recipient's profile image to the response
        profile_image = None
        if hasattr(other_user, 'profile') and other_user.profile.image:
            profile_image = request.build_absolute_uri(other_user.profile.image.url)

        response.data = {
            'messages': response.data,
            'recipient_profile_image': profile_image
        }

        return instance