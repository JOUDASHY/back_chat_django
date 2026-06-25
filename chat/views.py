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
from .models import Message, Room, Profile, Block
from .serializers import (
    MessageSerializer, RegisterSerializer, UserUpdateSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
    ConversationSerializer, UserSerializer, CurrentUserSerializer, CustomTokenObtainPairSerializer,
    RoomSerializer, RoomDetailSerializer
)
from .pusher_client import pusher_client
from .call_service import message_preview
from .utils import update_online_status, redis_client, redis_available, get_user_display_name, resolve_user_by_login_identifier

# Configure logger and environment
logger = logging.getLogger(__name__)
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

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
        ALLOWED_REDIRECTS = [
            f"{settings.FRONTEND_URL}/auth/google/callback",
            "com.chatbeast.app://auth/google/callback",
        ]

        redirect_uri = request.GET.get(
            "redirect_uri",
            f"{settings.FRONTEND_URL}/auth/google/callback"
        )

        if redirect_uri not in ALLOWED_REDIRECTS:
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

            if not user.is_active:
                return Response(
                    {'error': 'Ce compte est suspendu. Contactez un administrateur.'},
                    status=status.HTTP_403_FORBIDDEN,
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
                'is_staff': user.is_staff,
                'is_active': user.is_active,
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
        profile = user.profile

        if redis_available:
            update_online_status(user.id, is_online)

        now = timezone.now()

        if not is_online:
            # Déconnexion : sauvegarder last_online = maintenant
            profile.last_online = now
            profile.status = 'offline'
            profile.save(update_fields=['last_online', 'status'])
            pusher_client.trigger('presence-channel', 'user-status-changed', {
                'userId': user.id,
                'isOnline': False,
                'lastOnline': profile.last_online.isoformat(),
            })
        else:
            # Heartbeat : garder last_online à jour pendant la session (max 2 min d'écart)
            profile.last_online = now
            profile.status = 'online'
            profile.save(update_fields=['last_online', 'status'])

        return Response({"status": "online" if is_online else "offline"})

class HandleDisconnectView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        update_online_status(user.id, False)
        # Sauvegarder last_online = moment exact de la déconnexion
        profile = user.profile
        profile.last_online = timezone.now()
        profile.status = 'offline'
        profile.save(update_fields=['last_online', 'status'])
        # Notifier via Pusher
        pusher_client.trigger('presence-channel', 'user-status-changed', {
            'userId': user.id,
            'isOnline': False,
            'lastOnline': profile.last_online.isoformat(),
        })
        return Response({"status": "offline"})


class LoginView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            user = resolve_user_by_login_identifier(request.data.get('username'))
            if not user:
                return response
            profile = user.profile
            profile.status = 'online'
            profile.last_online = timezone.now()
            profile.save(update_fields=['status', 'last_online'])
            update_online_status(user.id, True)
            pusher_client.trigger('presence-channel', 'user-status-changed', {
                'userId': user.id,
                'isOnline': True,
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
    serializer_class = CurrentUserSerializer
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
        user = self.request.user
        
        # Obtenir les IDs des utilisateurs bloqués ou qui m'ont bloqué
        blocked_by_me = Block.objects.filter(blocker=user).values_list('blocked_id', flat=True)
        blocked_me = Block.objects.filter(blocked=user).values_list('blocker_id', flat=True)
        excluded_ids = set(blocked_by_me) | set(blocked_me)

        queryset = super().get_queryset().exclude(id__in=excluded_ids).select_related('profile')
        for u in queryset:
            u.is_online = bool(int(redis_client.get(f'user:{u.id}:online') or 0))
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

        # ID synthétique de la conversation privée
        a, b = sorted([user.id, other_user.id])
        conversation_id = int(f"{a}{b}")

        # Récupérer le dernier message existant (si la conversation existe déjà)
        last_message = Message.objects.filter(
            (Q(sender=user) & Q(recipient=other_user)) |
            (Q(sender=other_user) & Q(recipient=user)),
            room__isnull=True
        ).order_by('-timestamp').first()

        user_serializer = UserSerializer(other_user, context={'request': request})

        if last_message:
            # Conversation existante — retourner les données complètes
            unread_count = Message.objects.filter(
                sender=other_user, recipient=user, is_read=False
            ).count()
            return Response({
                'id': conversation_id,
                'name': get_user_display_name(other_user),
                'lastMessage': message_preview(last_message),
                'timestamp': last_message.timestamp,
                'isGroup': False,
                'userId': other_user.id,
                'unreadCount': unread_count,
                'lastMessageSeen': last_message.sender == user or last_message.is_read,
                'lastMessageSenderId': last_message.sender_id,
                'lastMessageIsRead': last_message.is_read,
                'user': user_serializer.data
            }, status=status.HTTP_200_OK)

        # Nouvelle conversation — créer un message d'initialisation
        message = Message.objects.create(
            sender=user,
            recipient=other_user,
            content="Conversation démarrée"
        )

        return Response({
            'id': conversation_id,
            'name': get_user_display_name(other_user),
            'lastMessage': message.content,
            'timestamp': message.timestamp,
            'isGroup': False,
            'userId': other_user.id,
            'unreadCount': 0,
            'lastMessageSeen': True,
            'lastMessageSenderId': user.id,
            'lastMessageIsRead': False,
            'user': user_serializer.data
        }, status=status.HTTP_201_CREATED)



class ConversationListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user

        # Conversations de groupe
        rooms = Room.objects.filter(participants=user).prefetch_related('participants__profile')
        group_data = []
        for room in rooms:
            last = (
                Message.objects
                .filter(room=room)
                .order_by('-timestamp')
                .first()
            )
            if last:
                # Participants avec leurs avatars (exclut l'user courant)
                participants = room.participants.exclude(id=user.id).select_related('profile')
                participants_data = [
                    {
                        'id': p.id,
                        'username': p.username,
                        'profile': {
                            'image': request.build_absolute_uri(p.profile.image.url)
                                     if p.profile.image else None,
                        }
                    }
                    for p in participants
                ]
                unread_count = Message.objects.filter(
                    room=room, is_read=False
                ).exclude(sender=user).count()

                group_data.append({
                    'id': room.id,
                    'name': room.name,
                    'lastMessage': message_preview(last),
                    'timestamp': last.timestamp,
                    'isGroup': True,
                    'user': None,
                    'participants': participants_data,
                    'unreadCount': unread_count,
                    'lastMessageSeen': last.sender_id == user.id or last.is_read,
                    'lastMessageSenderId': last.sender_id,
                    'lastMessageIsRead': last.is_read,
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
                
                unread_count = Message.objects.filter(sender=other_user, recipient=user, is_read=False).count()
                
                if last_message.sender == user:
                    last_message_seen = True
                else:
                    last_message_seen = last_message.is_read

                private_data.append({
                    'id': conversation_id,
                    'name': get_user_display_name(other_user),
                    'lastMessage': message_preview(last_message),
                    'timestamp': last_message.timestamp,
                    'isGroup': False,
                    'userId': other_user.id,
                    'unreadCount': unread_count,
                    'lastMessageSeen': last_message_seen,
                    'lastMessageSenderId': last_message.sender_id if last_message else None,
                    'lastMessageIsRead': last_message.is_read if last_message else True,
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
            .prefetch_related('reactions__user')\
            .order_by("timestamp")

    def create(self, request, *args, **kwargs):
        room_id = self.kwargs["room_id"]
        room = get_object_or_404(Room, pk=room_id)
        if not room.participants.filter(id=self.request.user.id).exists():
            raise PermissionDenied("Vous n'êtes pas un participant de cette room.")

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            msg = serializer.save(sender=self.request.user, room_id=room_id)
            # Sérialisation avec contexte
            message_data = MessageSerializer(msg, context={'request': request}).data
            pusher_client.trigger(f"group-chat-{room_id}", 'new-message', message_data)
            
            # Notifier la sidebar de tous les participants
            conversation_update = {
                'conversation': {
                    'id': room.id,
                    'name': room.name,
                    'lastMessage': message_preview(msg),
                    'timestamp': msg.timestamp.isoformat(),
                    'isGroup': True,
                    'lastMessageSeen': False,
                    'lastMessageSenderId': self.request.user.id,
                    'lastMessageIsRead': False,
                }
            }
            for participant in room.participants.all():
                pusher_client.trigger(
                    f"user-{participant.id}-conversations",
                    'new-message',
                    conversation_update
                )
                
            return Response(message_data, status=status.HTTP_201_CREATED)
        except IntegrityError as e:
            raise e

class RoomListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method == 'GET':
            return RoomDetailSerializer
        return RoomSerializer
        
    def get_queryset(self):
        return Room.objects.filter(participants=self.request.user)

    def perform_create(self, serializer):
        room = serializer.save()
        # Ajouter le créateur aux participants
        room.participants.add(self.request.user)
        # Ajouter les autres participants passés dans la requête
        participant_ids = self.request.data.get('participants', [])
        for pid in participant_ids:
            try:
                user = User.objects.get(id=pid)
                room.participants.add(user)
            except User.DoesNotExist:
                pass
                
        # Créer un message système d'initialisation pour que le groupe apparaisse
        msg = Message.objects.create(
            sender=self.request.user,
            room=room,
            content=f"Groupe '{room.name}' créé."
        )
        
        # Notifier tous les participants
        conversation_data = {
            'id': room.id,
            'name': room.name,
            'lastMessage': message_preview(msg),
            'timestamp': msg.timestamp.isoformat(),
            'isGroup': True,
            'unreadCount': 1,
            'lastMessageSeen': False,
            'lastMessageSenderId': self.request.user.id,
            'lastMessageIsRead': False,
        }
        
        for participant in room.participants.all():
            pusher_client.trigger(
                f"user-{participant.id}-conversations",
                'new-conversation',
                {'conversation': conversation_data}
            )

class RoomDetailUpdateView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.request.method in ['GET']:
            return RoomDetailSerializer
        return RoomSerializer
        
    def get_queryset(self):
        return Room.objects.filter(participants=self.request.user)
        
    def perform_update(self, serializer):
        room = serializer.save()
        participant_ids = self.request.data.get('participants')
        if participant_ids is not None:
            # Remplacer les participants par la nouvelle liste
            room.participants.clear()
            for pid in participant_ids:
                try:
                    user = User.objects.get(id=pid)
                    room.participants.add(user)
                except User.DoesNotExist:
                    pass
            
            # S'assurer que le créateur y reste au cas où (optionnel, mais recommandé)
            if not room.participants.filter(id=self.request.user.id).exists():
                room.participants.add(self.request.user)
            
            # Créer un message système pour informer du changement
            msg = Message.objects.create(
                sender=self.request.user,
                room=room,
                content=f"Les paramètres du groupe ont été mis à jour."
            )
            
            message_data = MessageSerializer(msg, context={'request': self.request}).data
            pusher_client.trigger(f"group-chat-{room.id}", 'new-message', message_data)
            
            # Notifier les conversations
            conversation_update = {
                'conversation': {
                    'id': room.id,
                    'name': room.name,
                    'lastMessage': message_preview(msg),
                    'timestamp': msg.timestamp.isoformat(),
                    'lastMessageSenderId': self.request.user.id,
                    'isGroup': True,
                    'lastMessageSeen': False,
                    'lastMessageIsRead': False,
                }
            }
            for participant in room.participants.all():
                pusher_client.trigger(
                    f"user-{participant.id}-conversations",
                    'new-message',
                    conversation_update
                )

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
         .prefetch_related('reactions__user')\
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

    def _private_sidebar_conversation(self, conversation_id, msg, peer_user, *, increment_unread, last_message_seen):
        """Payload complet pour la sidebar (nom, avatar, userId)."""
        return {
            'id': conversation_id,
            'name': get_user_display_name(peer_user),
            'lastMessage': message_preview(msg),
            'timestamp': msg.timestamp.isoformat(),
            'isGroup': False,
            'userId': peer_user.id,
            'user': UserSerializer(peer_user, context={'request': self.request}).data,
            'incrementUnread': increment_unread,
            'lastMessageSeen': last_message_seen,
            'lastMessageSenderId': self.request.user.id,
            'lastMessageIsRead': False,
        }

    def perform_create(self, serializer):
        other_id = self.kwargs["user_id"]
        other_user = get_object_or_404(User, pk=other_id)

        # Vérifier si un blocage existe dans un sens ou l'autre
        if Block.objects.filter(
            Q(blocker=self.request.user, blocked=other_user) |
            Q(blocker=other_user, blocked=self.request.user)
        ).exists():
            raise PermissionDenied("Impossible d'envoyer un message : blocage actif entre ces utilisateurs.")

        try:
            msg = serializer.save(sender=self.request.user, recipient_id=other_id)
            # Sérialisation avec contexte
            message_data = MessageSerializer(msg, context={'request': self.request}).data
            a, b = sorted([self.request.user.id, other_id])
            pusher_client.trigger(f"private-chat-{a}-{b}", 'new-message', message_data)
            
            # Notifier la sidebar des deux utilisateurs
            conversation_id = int(f"{a}{b}")
            
            # Pour l'expéditeur (peer = destinataire)
            pusher_client.trigger(
                f"user-{self.request.user.id}-conversations",
                'new-message',
                {
                    'conversation': self._private_sidebar_conversation(
                        conversation_id,
                        msg,
                        other_user,
                        increment_unread=False,
                        last_message_seen=True,
                    )
                }
            )
            
            # Pour le destinataire (peer = expéditeur)
            pusher_client.trigger(
                f"user-{other_id}-conversations",
                'new-message',
                {
                    'conversation': self._private_sidebar_conversation(
                        conversation_id,
                        msg,
                        self.request.user,
                        increment_unread=True,
                        last_message_seen=False,
                    )
                }
            )
            
            # Supprimer last_seen ici — il doit refléter la session, pas l'activité de messagerie
            # last_seen est mis à jour à la connexion et à la déconnexion
            
        except IntegrityError as e:
            raise e
        except ValidationError as e:
            print(f"Validation error: {e.detail}")
            raise e
        except Exception as e:
            print(f"Unexpected error: {e}")
            raise e


class MessageDetailView(APIView):
    """Modifier ou supprimer un message (auteur uniquement)."""
    permission_classes = [IsAuthenticated]

    def _trigger_message_event(self, event: str, payload, msg: Message):
        if msg.room_id:
            pusher_client.trigger(f"group-chat-{msg.room_id}", event, payload)
        elif msg.recipient_id:
            a, b = sorted([msg.sender_id, msg.recipient_id])
            pusher_client.trigger(f"private-chat-{a}-{b}", event, payload)

    def patch(self, request, pk):
        msg = get_object_or_404(Message, pk=pk)

        if msg.sender_id != request.user.id:
            raise PermissionDenied("Vous ne pouvez modifier que vos propres messages.")

        if msg.attachment:
            return Response(
                {"error": "Impossible de modifier un message avec pièce jointe."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content = request.data.get('content', '').strip()
        if not content:
            return Response(
                {"error": "Le message ne peut pas être vide."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        msg.content = content
        msg.save(update_fields=['content'])

        message_data = MessageSerializer(msg, context={'request': request}).data
        self._trigger_message_event('message-updated', message_data, msg)
        return Response(message_data)

    def delete(self, request, pk):
        msg = get_object_or_404(Message, pk=pk)

        if msg.sender_id != request.user.id:
            raise PermissionDenied("Vous ne pouvez supprimer que vos propres messages.")

        message_id = msg.id
        room_id = msg.room_id
        recipient_id = msg.recipient_id
        sender_id = msg.sender_id

        if msg.attachment:
            try:
                msg.attachment.delete(save=False)
            except Exception as e:
                logger.warning("Failed to delete attachment for message %s: %s", pk, e)

        msg.delete()

        payload = {'id': message_id}
        if room_id:
            pusher_client.trigger(f"group-chat-{room_id}", 'message-deleted', payload)
        elif recipient_id:
            a, b = sorted([sender_id, recipient_id])
            pusher_client.trigger(f"private-chat-{a}-{b}", 'message-deleted', payload)

        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageReactionView(APIView):
    """Ajouter, modifier ou retirer une réaction emoji sur un message."""
    permission_classes = [IsAuthenticated]

    def _trigger_reaction_event(self, msg: Message, payload: dict):
        if msg.room_id:
            pusher_client.trigger(f"group-chat-{msg.room_id}", 'message-reaction', payload)
        elif msg.recipient_id:
            a, b = sorted([msg.sender_id, msg.recipient_id])
            pusher_client.trigger(f"private-chat-{a}-{b}", 'message-reaction', payload)

    def post(self, request, pk):
        from .reaction_utils import (
            ALLOWED_REACTION_EMOJIS,
            toggle_message_reaction,
            user_can_react_to_message,
        )

        msg = get_object_or_404(
            Message.objects.select_related('room').prefetch_related('room__participants', 'reactions__user'),
            pk=pk,
        )

        if not user_can_react_to_message(msg, request.user):
            raise PermissionDenied("Vous ne pouvez pas réagir à ce message.")

        emoji = (request.data.get('emoji') or '').strip()
        if emoji not in ALLOWED_REACTION_EMOJIS:
            return Response({'error': 'Emoji de réaction invalide.'}, status=status.HTTP_400_BAD_REQUEST)

        reactions = toggle_message_reaction(message=msg, user=request.user, emoji=emoji)
        payload = {'message_id': msg.id, 'reactions': reactions}
        self._trigger_reaction_event(msg, payload)
        return Response(payload)


class TypingView(APIView):
    """Diffuser un indicateur de frappe via Pusher."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        is_typing = request.data.get('isTyping', False)
        channel = request.data.get('channel', '')
        if not channel:
            return Response({'detail': 'channel requis'}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        typing_payload = {
            'userId': user.id,
            'username': user.username,
            'isTyping': is_typing,
        }
        pusher_client.trigger(channel, 'typing', typing_payload)

        sidebar_payload = {
            **typing_payload,
            'display_name': get_user_display_name(user),
        }

        if channel.startswith('private-chat-'):
            try:
                a, b = [int(x) for x in channel.replace('private-chat-', '').split('-')]
            except (TypeError, ValueError):
                return Response({'ok': True})

            other_id = b if user.id == a else a
            sidebar_payload['conversation_id'] = int(f'{a}{b}')
            pusher_client.trigger(f'user-{other_id}-conversations', 'typing', sidebar_payload)

        elif channel.startswith('group-chat-'):
            try:
                room_id = int(channel.replace('group-chat-', ''))
            except (TypeError, ValueError):
                return Response({'ok': True})

            sidebar_payload['conversation_id'] = room_id
            room = Room.objects.filter(pk=room_id).prefetch_related('participants').first()
            if room:
                for member in room.participants.exclude(pk=user.id):
                    pusher_client.trigger(
                        f'user-{member.id}-conversations',
                        'typing',
                        sidebar_payload,
                    )

        return Response({'ok': True})


class MarkMessagesReadView(APIView):
    """Marquer tous les messages reçus d'un utilisateur comme lus"""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        now = timezone.now()
        updated_count = Message.objects.filter(
            sender_id=user_id,
            recipient=request.user,
            is_read=False
        ).update(is_read=True, read_at=now)

        if updated_count > 0:
            # Notifier le sender en temps réel que ses messages ont été lus
            a, b = sorted([request.user.id, user_id])
            conversation_id = int(f"{a}{b}")
            
            pusher_client.trigger(
                f"private-chat-{a}-{b}",
                'messages-read',
                {
                    'reader_id': request.user.id,
                    'read_at': now.isoformat()
                }
            )
            
            # Notifier la sidebar de l'expéditeur (le destinataire de ce call) pour enlever le gras (lastMessageSeen=True)
            pusher_client.trigger(
                f"user-{user_id}-conversations",
                'messages-read-sidebar',
                {
                    'conversation_id': conversation_id,
                    'reset_unread': False,
                    'lastMessageIsRead': True
                }
            )
            
            # Notifier la sidebar du lecteur pour remettre à zéro son compteur
            pusher_client.trigger(
                f"user-{request.user.id}-conversations",
                'messages-read-sidebar',
                {
                    'conversation_id': conversation_id,
                    'reset_unread': True,
                    'lastMessageIsRead': True
                }
            )

        return Response({'marked_read': updated_count})


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
        online_users = []
        current_user_id = request.user.id

        # Obtenir les IDs des utilisateurs bloqués ou qui m'ont bloqué
        blocked_by_me = Block.objects.filter(blocker=request.user).values_list('blocked_id', flat=True)
        blocked_me = Block.objects.filter(blocked=request.user).values_list('blocker_id', flat=True)
        excluded_ids = set(blocked_by_me) | set(blocked_me)

        if redis_available and redis_client:
            for key in redis_client.keys('user:*:online'):
                if str(redis_client.get(key)) != '1':
                    continue
                try:
                    # Gérer si key est en bytes ou string
                    decoded_key = key.decode('utf-8') if isinstance(key, bytes) else key
                    user_id = int(decoded_key.split(':')[1])
                except (IndexError, ValueError, AttributeError):
                    continue
                if user_id == current_user_id or user_id in excluded_ids:
                    continue
                try:
                    user = User.objects.select_related('profile').get(id=user_id)
                    user.is_online = True
                    online_users.append(
                        UserSerializer(user, context={'request': request}).data
                    )
                except User.DoesNotExist:
                    pass

        online_users.sort(
            key=lambda u: (u.get('display_name') or u.get('username') or '').lower()
        )
        return Response(online_users)


# Nouvelle vue pour les préférences utilisateur
class UserPreferencesView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user

class BlockUserView(APIView):
    """Bloquer un utilisateur."""
    permission_classes = [IsAuthenticated]

    def post(self, request, user_id):
        if request.user.id == user_id:
            return Response(
                {'error': 'Vous ne pouvez pas vous bloquer vous-même.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target = get_object_or_404(User, pk=user_id)
        block, created = Block.objects.get_or_create(blocker=request.user, blocked=target)
        if created:
            return Response({'detail': f'{target.username} a été bloqué.'}, status=status.HTTP_201_CREATED)
        return Response({'detail': 'Utilisateur déjà bloqué.'}, status=status.HTTP_200_OK)


class UnblockUserView(APIView):
    """Débloquer un utilisateur."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        deleted, _ = Block.objects.filter(blocker=request.user, blocked=target).delete()
        if deleted:
            return Response({'detail': f'{target.username} a été débloqué.'}, status=status.HTTP_200_OK)
        return Response({'detail': 'Cet utilisateur n\'était pas bloqué.'}, status=status.HTTP_404_NOT_FOUND)


class BlockStatusView(APIView):
    """Statut de blocage entre l'utilisateur connecté et un autre."""
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        target = get_object_or_404(User, pk=user_id)
        i_blocked = Block.objects.filter(blocker=request.user, blocked=target).exists()
        they_blocked = Block.objects.filter(blocker=target, blocked=request.user).exists()
        return Response({
            'i_blocked_them': i_blocked,
            'they_blocked_me': they_blocked,
            'is_blocked': i_blocked or they_blocked,
        })


class BlockedUsersListView(generics.ListAPIView):
    """Liste des utilisateurs bloqués par l'utilisateur connecté."""
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_queryset(self):
        blocked_ids = Block.objects.filter(blocker=self.request.user).values_list('blocked_id', flat=True)
        return User.objects.filter(id__in=blocked_ids).select_related('profile')


class ForwardMessageView(APIView):
    """Transférer un message vers un autre utilisateur ou un groupe."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        from django.core.files.base import ContentFile
        import os
        from .call_service import message_preview

        # Vérifier que le message existe
        original_msg = get_object_or_404(Message, pk=pk)

        recipient_id = request.data.get('recipient_id')
        room_id = request.data.get('room_id')

        if not recipient_id and not room_id:
            return Response(
                {"error": "recipient_id ou room_id est requis."},
                status=status.HTTP_400_BAD_REQUEST
            )

        new_msg = Message(
            sender=request.user,
            content=original_msg.content,
        )

        # Vérifier les permissions et affecter le destinataire/groupe
        if room_id:
            room = get_object_or_404(Room, pk=room_id)
            if not room.participants.filter(id=request.user.id).exists():
                raise PermissionDenied("Vous n'êtes pas membre de ce groupe.")
            new_msg.room = room
        else:
            recipient = get_object_or_404(User, pk=recipient_id)
            new_msg.recipient = recipient
            
        new_msg.save()

        # Gérer la pièce jointe
        if original_msg.attachment:
            try:
                # On copie le fichier
                file_name = os.path.basename(original_msg.attachment.name)
                # Le save=True sauvegardera le nouveau nom/chemin dans l'objet
                new_msg.attachment.save(file_name, ContentFile(original_msg.attachment.read()), save=True)
            except Exception as e:
                print(f"Erreur lors de la copie de la pièce jointe: {e}")

        # Notifier via Pusher
        message_data = MessageSerializer(new_msg, context={'request': request}).data
        
        preview = message_preview(new_msg)
        ts = new_msg.timestamp.isoformat()

        if new_msg.room:
            pusher_client.trigger(f"group-chat-{new_msg.room.id}", 'new-message', message_data)
            for participant in new_msg.room.participants.all():
                pusher_client.trigger(
                    f"user-{participant.id}-conversations",
                    'new-message',
                    {
                        'conversation': {
                            'id': new_msg.room.id,
                            'lastMessage': preview,
                            'timestamp': ts,
                            'incrementUnread': participant.id != request.user.id,
                            'lastMessageSeen': participant.id == request.user.id,
                            'lastMessageSenderId': request.user.id,
                            'lastMessageIsRead': False,
                        }
                    }
                )
        elif new_msg.recipient:
            a, b = sorted([request.user.id, new_msg.recipient.id])
            pusher_client.trigger(f"private-chat-{a}-{b}", 'new-message', message_data)
            conversation_id = int(f"{a}{b}")

            for uid, is_recipient in [(request.user.id, False), (new_msg.recipient.id, True)]:
                pusher_client.trigger(
                    f"user-{uid}-conversations",
                    'new-message',
                    {
                        'conversation': {
                            'id': conversation_id,
                            'lastMessage': preview,
                            'timestamp': ts,
                            'incrementUnread': is_recipient,
                            'lastMessageSeen': not is_recipient,
                            'lastMessageSenderId': request.user.id,
                            'lastMessageIsRead': False,
                        }
                    }
                )

        return Response(message_data, status=status.HTTP_201_CREATED)
