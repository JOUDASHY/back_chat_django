# chat/serializers.py

from rest_framework import serializers
from .models import Message
from django.contrib.auth import get_user_model
# from django.contrib.auth.models import User
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.models import User
# from rest_framework import serializers
from .models import Profile, ProfileImage
# serializers.py
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework.exceptions import AuthenticationFailed

from .utils import get_user_display_name, generate_unique_username, resolve_user_by_login_identifier

from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.template.loader import render_to_string
from django.core.mail import send_mail
from django.conf import settings
# Dans chat/serializers.py



# serializers.py
# serializers.py
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Connexion par email ou identifiant (@username)."""

    def validate(self, attrs):
        identifier = (attrs.get('username') or '').strip()
        password = attrs.get('password')

        user = resolve_user_by_login_identifier(identifier)

        if not user or not user.check_password(password):
            raise AuthenticationFailed(
                'Identifiants incorrects. Utilisez votre email ou votre identifiant.'
            )

        if not user.is_active:
            raise AuthenticationFailed(
                'Ce compte est suspendu. Contactez un administrateur.',
                code='account_suspended',
            )

        self.user = user
        refresh = self.get_token(user)
        data = {
            'refresh': str(refresh),
            'access': str(refresh.access_token),
        }
        user_serializer = CurrentUserSerializer(
            instance=user,
            context={'request': self.context.get('request')}
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
            'social_links', 'last_seen', 'last_online', 'is_verified', 'theme_preference',
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
from .reaction_utils import serialize_message_reactions

User = get_user_model()
# from rest_framework import serializers
# from django.contrib.auth import get_user_model
from .models import Room

# User = get_user_model()
# from django.contrib.auth.models import User
# from rest_framework import serializers

class UserSerializer(serializers.ModelSerializer):
    profile = ProfileSerializer(read_only=True)
    is_online = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'last_name',
            'display_name', 'profile', 'is_online'
        )

    def get_display_name(self, obj):
        return get_user_display_name(obj)

    def get_is_online(self, obj):
        if obj.username == 'assistant':
            return True
        try:
            from .utils import redis_client
            val = redis_client.get(f'user:{obj.id}:online')
            return bool(int(val or 0))
        except Exception:
            return False


class CurrentUserSerializer(UserSerializer):
    is_staff = serializers.BooleanField(read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ('is_staff', 'is_active')

class ConversationCreateSerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=True)

class ConversationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    lastMessage = serializers.CharField()
    timestamp = serializers.DateTimeField()
    isGroup = serializers.BooleanField()
    userId = serializers.IntegerField(required=False)
    unreadCount = serializers.IntegerField(required=False, default=0)
    lastMessageSeen = serializers.BooleanField(required=False, default=True)
    lastMessageSenderId = serializers.IntegerField(required=False, allow_null=True)
    lastMessageIsRead = serializers.BooleanField(required=False, default=True)

class MessageSerializer(serializers.ModelSerializer):
    sender = serializers.StringRelatedField(read_only=True)
    sender_profile = serializers.SerializerMethodField(read_only=True)
    recipient = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False, allow_null=True
    )
    room = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(),
        required=False, allow_null=True
    )
    parent = serializers.PrimaryKeyRelatedField(
        queryset=Message.objects.all(),
        required=False,
        allow_null=True,
    )
    parent_message = serializers.SerializerMethodField(read_only=True)
    replies_count = serializers.SerializerMethodField(read_only=True)
    # allow_blank=True so file-only messages don't fail validation
    content = serializers.CharField(required=False, allow_blank=True, default='')
    attachment = serializers.FileField(required=False, allow_null=True)
    reactions = serializers.SerializerMethodField(read_only=True)
    is_favorite = serializers.SerializerMethodField(read_only=True)
    is_pinned = serializers.SerializerMethodField(read_only=True)

    def _saved_flag(self, obj, field: str) -> bool:
        from .models import SavedMessage
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        return SavedMessage.objects.filter(
            user=request.user, message=obj, **{field: True}
        ).exists()

    def get_is_favorite(self, obj):
        return self._saved_flag(obj, 'is_favorite')

    def get_is_pinned(self, obj):
        return self._saved_flag(obj, 'is_pinned')

    def get_reactions(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user or not user.is_authenticated:
            return []
        return serialize_message_reactions(obj, user)

    def get_sender_profile(self, obj):
        request = self.context.get('request')
        try:
            profile = obj.sender.profile
            image_url = None
            if profile.image:
                image_url = request.build_absolute_uri(profile.image.url) if request else profile.image.url
            return {'image': image_url}
        except Exception:
            return {'image': None}

    def get_parent_message(self, obj):
        if not obj.parent:
            return None
        request = self.context.get('request')
        parent = obj.parent
        sender_profile = None
        try:
            profile = parent.sender.profile
            if profile.image:
                sender_profile = {'image': request.build_absolute_uri(profile.image.url) if request else profile.image.url}
        except Exception:
            sender_profile = {'image': None}

        return {
            'id': parent.id,
            'sender': str(parent.sender),
            'content': parent.content,
            'sender_profile': sender_profile,
        }

    def get_replies_count(self, obj):
        return obj.replies.count()

    def validate(self, attrs):
        if attrs.get('call_event'):
            return attrs
        if not attrs.get('content', '').strip() and not attrs.get('attachment'):
            raise serializers.ValidationError(
                {'content': 'Un message doit contenir du texte ou une pièce jointe.'}
            )
        return attrs

    class Meta:
        model = Message
        fields = [
            "id", "sender", "sender_profile", "recipient", "room", "parent", "parent_message", "replies_count", "content",
            "timestamp", "attachment", "is_read", "read_at", "call_event", "reactions",
            "is_favorite", "is_pinned",
        ]
        read_only_fields = ["id", "sender", "sender_profile", "timestamp", "is_read", "read_at", "reactions", "parent_message", "replies_count"]

        
             
class RoomSerializer(serializers.ModelSerializer):
    participants = serializers.PrimaryKeyRelatedField(
        many=True, queryset=User.objects.all(), required=False
    )

    class Meta:
        model = Room
        fields = ["id", "name", "participants"]

class RoomDetailSerializer(serializers.ModelSerializer):
    participants = UserSerializer(many=True, read_only=True)

    class Meta:
        model = Room
        fields = ["id", "name", "participants"]

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    gender = serializers.CharField(write_only=True, required=False)
    username = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'gender', 'first_name', 'last_name')
        extra_kwargs = {
            'first_name': {'required': False},
            'last_name': {'required': True},
            'email': {'required': True},
        }

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('Cet email est déjà utilisé.')
        return value

    def create(self, validated_data):
        gender = validated_data.pop('gender', None)
        validated_data.pop('username', None)
        email = validated_data['email']
        first_name = validated_data.get('first_name', '').strip()
        last_name = validated_data.get('last_name', '').strip()

        username = generate_unique_username(email.split('@')[0])

        user = User.objects.create_user(
            username=username,
            email=email,
            password=validated_data['password'],
            first_name=first_name,
            last_name=last_name,
        )

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

        return instance


class ProfileImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProfileImage
        fields = ['id', 'image', 'image_url', 'caption', 'order', 'created_at']
        read_only_fields = ['id', 'created_at', 'image_url']

    def get_image_url(self, obj):
        if obj.image and 'request' in self.context:
            return self.context['request'].build_absolute_uri(obj.image.url)
        return None

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)