# Standard library imports
import os
import logging
import requests
import uuid
import redis
from datetime import datetime

# Django imports
from django.db import transaction, IntegrityError
from django.conf import settings
from django.contrib.auth import login, authenticate
from django.contrib.auth.models import User
from django.contrib.auth.backends import ModelBackend
from django.core.files.base import ContentFile
from django.db.utils import DatabaseError
from django.shortcuts import get_object_or_404
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.db.models import Q, Max

# Rest framework imports
from rest_framework import generics, permissions, status, parsers, filters
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import RetrieveAPIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken

# Third party imports
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException

# Local imports
from .models import Message, Room, Profile
from .serializers import (
    MessageSerializer, RegisterSerializer, UserUpdateSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    ConversationSerializer, UserSerializer, CustomTokenObtainPairSerializer
)
from .pusher_client import pusher_client
from .utils import update_online_status, redis_available

# Configure logger and environment
logger = logging.getLogger(__name__)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    db=settings.REDIS_DB,
    password=settings.REDIS_PASSWORD
)

class GoogleAuthView(APIView):
    def get(self, request):
        # Récupération sécurisée des clés depuis les variables d'environnement
        google_client_id = os.getenv('GOOGLE_CLIENT_ID')
        google_client_secret = os.getenv('GOOGLE_CLIENT_SECRET')

        if not google_client_id or not google_client_secret:
            logger.error("Google OAuth credentials not found in environment variables")
            return Response(
                {"error": "OAuth configuration missing"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # ⇩ ici, on pointe sur le front
        redirect_uri = f"{settings.FRONTEND_URL}/auth/google/callback"

        scopes = [
            'openid',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
        ]

        # 1️⃣ Pas de code → on demande l'URL d'auth
        if 'code' not in request.GET:
            oauth = OAuth2Session(
                google_client_id,
                redirect_uri=redirect_uri,
                scope=scopes
            )
            auth_url, state = oauth.authorization_url(
                'https://accounts.google.com/o/oauth2/auth',
                access_type='offline',
                prompt='select_account',
            )
            request.session['oauth_state'] = state
            return Response({'authorization_url': auth_url})

        # 2️⃣ Avec code → on traite comme avant
        oauth = OAuth2Session(
            google_client_id,
            redirect_uri=redirect_uri,
            scope=scopes
        )
        token_data = oauth.fetch_token(
            'https://oauth2.googleapis.com/token',
            client_secret=google_client_secret,
            authorization_response=request.build_absolute_uri(),
        )
        user_info = oauth.get(
            'https://www.googleapis.com/oauth2/v3/userinfo'
        ).json()

        # Get profile image from Google
        picture_url = user_info.get('picture')
        
        # Wrap user creation and profile setup in a transaction
        with transaction.atomic():
            user, created = User.objects.get_or_create(
                email=user_info['email'],
                defaults={
                    'username': user_info['email'].split('@')[0],
                    'first_name': user_info.get('given_name', ''),
                    'last_name': user_info.get('family_name', ''),
                }
            )

            # Create profile if it doesn't exist
            profile, profile_created = Profile.objects.get_or_create(
                user=user,
                defaults={
                    'notification_preferences': {
                        'message_notifications': True,
                        'group_notifications': True,
                        'sound_enabled': True,
                        'email_notifications': True
                    },
                    'status': 'online',
                    'is_verified': user_info.get('email_verified', False),
                    'language_preference': user_info.get('locale', 'fr')[:2] if user_info.get('locale') else 'fr'
                }
            )

            # Mise à jour de l'image de profil depuis Google
            if picture_url:  # Retirer les conditions qui empêchent la mise à jour
                try:
                    response = requests.get(picture_url)
                    if response.status_code == 200:
                        # Création du dossier avatars si nécessaire
                        avatar_dir = os.path.join(settings.MEDIA_ROOT, 'avatars')
                        os.makedirs(avatar_dir, exist_ok=True)

                        # Supprimer l'ancienne image si elle existe
                        if profile.image:
                            try:
                                old_path = os.path.join(settings.MEDIA_ROOT, str(profile.image))
                                if os.path.exists(old_path):
                                    os.remove(old_path)
                            except Exception as e:
                                logger.error(f"Erreur suppression ancienne image: {e}")

                        # Sauvegarder la nouvelle image
                        image_name = f"{user.id}_google.jpg"
                        file_path = f"avatars/{image_name}"
                        
                        # Créer et sauvegarder le fichier
                        with open(os.path.join(settings.MEDIA_ROOT, file_path), 'wb') as f:
                            f.write(response.content)

                        # Mettre à jour le chemin dans la base de données
                        profile.image = file_path
                        profile.save(update_fields=['image'])

                        # Vérifier que l'image est bien sauvegardée
                        if not os.path.exists(os.path.join(settings.MEDIA_ROOT, file_path)):
                            raise Exception("L'image n'a pas été sauvegardée")

                except Exception as e:
                    logger.error(f"Erreur sauvegarde image: {str(e)}")
                    logger.exception(e)

            profile.last_seen = timezone.now()
            profile.save()

        user.backend = 'django.contrib.auth.backends.ModelBackend'
        login(request, user)

        refresh = RefreshToken.for_user(user)

        # Include full profile data in response
        profile_data = {
            'image': request.build_absolute_uri(profile.image.url) if profile.image else None,
            'cover_image': request.build_absolute_uri(profile.cover_image.url) if profile.cover_image else None,
            'bio': profile.bio,
            'lieu': profile.lieu,
            'date_naiv': profile.date_naiv,
            'gender': profile.gender,
            'phone_number': profile.phone_number,
            'status': profile.status,
            'passion': profile.passion,
            'profession': profile.profession,
            'website': profile.website,
            'social_links': profile.social_links,
            'last_seen': profile.last_seen,
            'is_verified': profile.is_verified,
            'theme_preference': profile.theme_preference,
            'language_preference': profile.language_preference,
            'notification_preferences': profile.notification_preferences,
            'age': profile.age() if profile.date_naiv else None
        }

        return Response({
            'access_token': str(refresh.access_token),
            'refresh_token': str(refresh),
            'user': {
                'id': user.id,
                'email': user.email,
                'username': user.username,
                'firstName': user.first_name,
                'lastName': user.last_name,
                'profile': profile_data
            }
        })




class PasswordResetRequestView(APIView):
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"detail": "Email de réinitialisation envoyé"},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetConfirmView(APIView):
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(
                {"detail": "Mot de passe réinitialisé avec succès"},
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UpdateOnlineStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        is_online = request.data.get('isOnline', True)

        if redis_available:
            update_online_status(user.id, is_online)
        else:
            # Fallback si Redis n'est pas disponible
            user.profile.status = 'online' if is_online else 'offline'
            user.profile.save()

        return Response({"status": "online" if is_online else "offline"})

class HandleDisconnectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        update_online_status(user.id, False)
        return Response({"status": "offline"})



class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        # Mettre à jour le statut et last_seen lors de la connexion
        if response.status_code == 200:
            user = User.objects.get(username=request.data.get('username'))
            profile = user.profile
            profile.status = 'online'
            profile.save()
            update_online_status(user.id, True)

            # Déclencher un événement Pusher
            pusher_client.trigger('presence-channel', 'user-status-changed', {
                'userId': user.id,
                'isOnline': True
            })

        return response

class PublicUserProfileView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]  # Ou [permissions.AllowAny] pour un accès public
    queryset = User.objects.all()
    lookup_field = 'pk'

    def get_queryset(self):
        return super().get_queryset().select_related('profile')

class CurrentUserView(generics.RetrieveAPIView):
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user  # Retourne toujours l'utilisateur connecté

class UpdateProfileView(generics.UpdateAPIView):
    serializer_class = UserUpdateSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.JSONParser]  # Pour les images et JSON

    def get_object(self):
        return self.request.user  # Retourne toujours l'utilisateur connecté

    def perform_update(self, serializer):
        # Ajoutez ici des validations personnalisées si nécessaire
        serializer.save()
        
        # Mettre à jour le statut en ligne si nécessaire
        profile_data = self.request.data.get('profile', {})
        if 'status' in profile_data:
            status_value = profile_data['status']
            is_online = status_value == 'online'
            update_online_status(self.request.user.id, is_online)



class UserDetailView(RetrieveAPIView):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'pk'  # pour permettre /user/1/


class UserListView(generics.ListAPIView):
    queryset = User.objects.all().order_by('username')
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Active le paramètre ?search=<terme>
    filter_backends = [filters.SearchFilter]
    search_fields = ['username', 'first_name', 'last_name', 'email', 'profile__profession', 'profile__lieu']

    def get_queryset(self):
        queryset = super().get_queryset().select_related('profile')
        for user in queryset:
            user.is_online = bool(int(redis_client.get(f'user:{user.id}:online') or 0))
        return queryset


class ConversationCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        other_id = request.data.get('user_id')
        
        try:
            other_user = User.objects.get(pk=other_id)
        except User.DoesNotExist:
            return Response({'detail': 'Utilisateur introuvable'}, status=status.HTTP_404_NOT_FOUND)

        # Vérifie si une conversation existe déjà
        existing_conversation = Message.objects.filter(
            (Q(sender=user) & Q(recipient=other_user)) |
            (Q(sender=other_user) & Q(recipient=user))
        ).first()

        if existing_conversation:
            return Response({'detail': 'Conversation déjà existante'}, status=status.HTTP_200_OK)

        # Crée un premier message vide pour initialiser la conversation
        message = Message.objects.create(
            sender=user,
            recipient=other_user,
            content="Conversation démarrée"
        )

        # Sérialiser l'utilisateur avec son profil
        user_serializer = UserSerializer(
            other_user,
            context={'request': request}
        )

        return Response({
            'id': f"{user.id}{other_user.id}",
            'name': other_user.username,
            'lastMessage': message.content,
            'timestamp': message.timestamp,
            'isGroup': False,
            'userId': other_user.id,
            'user': user_serializer.data
        }, status=status.HTTP_201_CREATED)



class ConversationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # Conversations de groupe
        rooms = Room.objects.filter(participants=user)
        group_data = []
        for room in rooms:
            last = (
                Message.objects
                .filter(room=room)
                .order_by('-timestamp')
                .values('content', 'timestamp')
                .first()
            )
            if last:
                group_data.append({
                    'id': room.id,
                    'name': room.name,
                    'lastMessage': last['content'],
                    'timestamp': last['timestamp'],
                    'isGroup': True,
                })

        # Conversations privées
        other_users = User.objects.filter(
            Q(sent_messages__recipient=user) | Q(received_messages__sender=user)
        ).distinct()

        private_data = []
        for other_user in other_users:
            last_message = Message.objects.filter(
                (Q(sender=user, recipient=other_user) | Q(sender=other_user, recipient=user)),
                room__isnull=True
            ).order_by('-timestamp').first()

            if last_message:
                a, b = sorted([user.id, other_user.id])
                conversation_id = int(f"{a}{b}")

                other_user.is_online = bool(int(redis_client.get(f'user:{other_user.id}:online') or 0))
                user_serializer = UserSerializer(other_user, context={'request': request})

                private_data.append({
                    'id': conversation_id,
                    'name': other_user.username,
                    'lastMessage': last_message.content,
                    'timestamp': last_message.timestamp,
                    'isGroup': False,
                    'userId': other_user.id,
                    'user': user_serializer.data
                })

        data = group_data + private_data
        data.sort(key=lambda c: c['timestamp'], reverse=True)
        return Response(data)

class GroupChatView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.JSONParser]  # Add these parsers

    def get_queryset(self):
        room_id = self.kwargs["room_id"]
        return Message.objects.filter(room_id=room_id)\
            .select_related('sender__profile', 'recipient__profile')\
            .order_by("timestamp")

    def perform_create(self, serializer):
        room_id = self.kwargs["room_id"]
        room = get_object_or_404(Room, pk=room_id)
        if not room.participants.filter(id=self.request.user.id).exists():
            raise PermissionDenied("Vous n'êtes pas un participant de cette room.")

        try:
            msg = serializer.save(sender=self.request.user, room_id=room_id)
            # Sérialisation avec contexte
            message_data = MessageSerializer(msg, context={'request': self.request}).data
            pusher_client.trigger(f"group-chat-{room_id}", 'new-message', message_data)
        except IntegrityError as e:
            raise e

class PrivateChatView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.JSONParser]

    def get_queryset(self):
        other_id = self.kwargs["user_id"]
        user = self.request.user
        return Message.objects.filter(
            Q(sender=user, recipient_id=other_id) |
            Q(sender_id=other_id, recipient=user)
        ).select_related('sender__profile', 'recipient__profile')\
         .order_by("timestamp")
    
    def list(self, request, *args, **kwargs):
        # Get the standard response with messages
        response = super().list(request, *args, **kwargs)
        
        # Get recipient user and their profile data
        other_id = self.kwargs["user_id"]
        other_user = get_object_or_404(User, pk=other_id)
        
        # Create a serialized version of the recipient user
        user_serializer = UserSerializer(other_user, context={'request': request})
        
        # Add the recipient data to the response
        response.data = {
            'messages': response.data,
            'recipient': user_serializer.data
        }
        
        return response

    def perform_create(self, serializer):
        other_id = self.kwargs["user_id"]
        other_user = get_object_or_404(User, pk=other_id)

        try:
            msg = serializer.save(sender=self.request.user, recipient_id=other_id)
            # Sérialisation avec contexte
            message_data = MessageSerializer(msg, context={'request': self.request}).data
            a, b = sorted([self.request.user.id, other_id])
            pusher_client.trigger(f"private-chat-{a}-{b}", 'new-message', message_data)
            
            # Mettre à jour last_seen pour l'expéditeur
            self.request.user.profile.last_seen = timezone.now()
            self.request.user.profile.save()
            
        except IntegrityError as e:
            raise e
        except ValidationError as e:
            print(f"Validation error: {e.detail}")
            raise e
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise e


class RegisterView(APIView):
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            
            # Récupérer le sexe depuis la requête
            gender = request.data.get('gender')
            
            # Initialiser le profil avec les valeurs par défaut et le sexe
            profile = user.profile
            profile.gender = gender
            profile.notification_preferences = {
                'message_notifications': True,
                'group_notifications': True,
                'sound_enabled': True,
                'email_notifications': False
            }
            profile.save()
            
            return Response({
                "message": "Utilisateur créé avec succès",
                "user_id": user.id,
                "username": user.username
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MessageListCreateView(generics.ListCreateAPIView):
    queryset = Message.objects.all().order_by('timestamp')
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [parsers.MultiPartParser, parsers.JSONParser]  # Add these parsers

    def perform_create(self, serializer):
        serializer.save(sender=self.request.user)


class PusherAuthView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        channel_name = request.data.get('channel_name')
        socket_id = request.data.get('socket_id')
        
        # Inclure des informations supplémentaires sur l'utilisateur
        user_info = {
            'user_id': request.user.id,
            'user_info': {
                'id': request.user.id,
                'name': request.user.username,
                'email': request.user.email,
                'status': request.user.profile.status,
                'image': request.build_absolute_uri(request.user.profile.image.url) if request.user.profile.image else None
            }
        }
        
        auth = pusher_client.authenticate(
            channel=channel_name,
            socket_id=socket_id,
            custom_data=user_info
        )
        return Response(auth)


# Nouvelle vue pour obtenir les utilisateurs en ligne
class OnlineUsersView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        # Récupérer tous les utilisateurs en ligne
        online_users = []
        for key in redis_client.keys('user:*:online'):
            if redis_client.get(key) == b'1':
                user_id = key.decode('utf-8').split(':')[1]
                try:
                    user = User.objects.get(id=user_id)
                    user_serializer = UserSerializer(user, context={'request': request})
                    online_users.append(user_serializer.data)
                except User.DoesNotExist:
                    pass
        
        return Response(online_users)


# Nouvelle vue pour les préférences utilisateur
class UserPreferencesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user