# Dans chat/urls.py

from django.urls import path
from .views import (
    RegisterView,
    MessageListCreateView,
    PrivateChatView,
    GroupChatView,
    ConversationListView,
    UserListView,
    PusherAuthView,
    UserDetailView,
    ConversationCreateView,
    UpdateProfileView,
    CurrentUserView,
    PublicUserProfileView,HandleDisconnectView,
    UpdateOnlineStatusView  # Ajoutez cette ligne
)

app_name = 'chat'

urlpatterns = [
    # Inscription (si vous remettez RegisterView en service)
    # path('register/', RegisterView.as_view(), name='register'),

    # Tous les messages (non filtrés)
    path('messages/', MessageListCreateView.as_view(), name='messages'),
    path('users/', UserListView.as_view(), name='user-list'),

    # Chat privé avec un autre utilisateur
    path('private/<int:user_id>/', PrivateChatView.as_view(), name='private-chat'),

    # Chat de groupe dans une room
    path('group/<int:room_id>/', GroupChatView.as_view(), name='group-chat'),

    # Authentification Pusher pour channels privés
    path('pusher/auth/', PusherAuthView.as_view(), name='pusher-auth'),

    # Liste des conversations
    path('conversations/', ConversationListView.as_view(), name='conversations'),
    path('users/<int:pk>/', PublicUserProfileView.as_view(), name='public-user-profile'),

    # Création de conversations
    path('conversations/create/', ConversationCreateView.as_view(), name='conversations-create'),
    path('me/', CurrentUserView.as_view(), name='current-user'),

    # Détails de l'utilisateur
    path('user/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('profile/', UpdateProfileView.as_view(), name='update-profile'),

    # Mise à jour du statut en ligne
    path('update-online-status/', UpdateOnlineStatusView.as_view(), name='update-online-status'),  # Ajoutez cette ligne
     path('update-online-status/', UpdateOnlineStatusView.as_view(), name='update-online-status'),
    path('handle-disconnect/', HandleDisconnectView.as_view(), name='handle-disconnect'),  # Ajoutez cette ligne

    # (Optionnel) Création et listing de rooms
    # path('rooms/', RoomListCreateView.as_view(), name='rooms'),
]
