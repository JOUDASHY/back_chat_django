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
    PublicUserProfileView, HandleDisconnectView,
    UpdateOnlineStatusView,
    OnlineUsersView,
    MarkMessagesReadView,
    RoomListCreateView,
    RoomDetailUpdateView,
    MessageDetailView,
    MessageReactionView,
    TypingView,
    BlockUserView,
    UnblockUserView,
    BlockStatusView,
    BlockedUsersListView,
    ForwardMessageView,
    ProfileImageView,
    ProfileImageDeleteView,
)
from .call_views import CallStartView, CallRespondView, CallEndView, CallHistoryView

app_name = 'chat'

urlpatterns = [
    # Inscription (si vous remettez RegisterView en service)
    # path('register/', RegisterView.as_view(), name='register'),

    # Tous les messages (non filtrés)
    path('messages/', MessageListCreateView.as_view(), name='messages'),
    path('messages/<int:pk>/', MessageDetailView.as_view(), name='message-detail'),
    path('messages/<int:pk>/reactions/', MessageReactionView.as_view(), name='message-reaction'),
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/online/', OnlineUsersView.as_view(), name='online-users'),
    path('messages/<int:pk>/forward/', ForwardMessageView.as_view(), name='message-forward'),

    # Chat privé avec un autre utilisateur
    path('private/<int:user_id>/', PrivateChatView.as_view(), name='private-chat'),
    path('private/<int:user_id>/read/', MarkMessagesReadView.as_view(), name='mark-messages-read'),

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
    path('update-online-status/', UpdateOnlineStatusView.as_view(), name='update-online-status'),
    path('handle-disconnect/', HandleDisconnectView.as_view(), name='handle-disconnect'),

    # Création et listing de rooms
    path('rooms/', RoomListCreateView.as_view(), name='rooms'),
    path('rooms/<int:pk>/', RoomDetailUpdateView.as_view(), name='room-detail'),
    path('typing/', TypingView.as_view(), name='typing'),

    # Appels audio / vidéo (LiveKit)
    path('calls/start/', CallStartView.as_view(), name='call-start'),
    path('calls/respond/', CallRespondView.as_view(), name='call-respond'),
    path('calls/end/', CallEndView.as_view(), name='call-end'),
    path('calls/history/', CallHistoryView.as_view(), name='call-history'),

    # Images de collection du profil
    path('profile/images/', ProfileImageView.as_view(), name='profile-images'),
    path('profile/images/<int:user_id>/', ProfileImageView.as_view(), name='profile-images-user'),
    path('profile/images/delete/<int:pk>/', ProfileImageDeleteView.as_view(), name='profile-image-delete'),

    # Blocage utilisateur
    path('users/<int:user_id>/block/', BlockUserView.as_view(), name='block-user'),
    path('users/<int:user_id>/unblock/', UnblockUserView.as_view(), name='unblock-user'),
    path('users/<int:user_id>/block-status/', BlockStatusView.as_view(), name='block-status'),
    path('users/blocked/', BlockedUsersListView.as_view(), name='blocked-users'),
]
