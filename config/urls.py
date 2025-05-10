# config/urls.py
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    
)
from django.urls import path
from chat.views import GoogleAuthView


from chat.views import RegisterView,LoginView,PasswordResetRequestView,PasswordResetConfirmView
from django.conf import settings
from django.conf.urls.static import static
urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/token/', LoginView.as_view(), name='token_obtain_pair'),
 path('api/password-reset/', PasswordResetRequestView.as_view(), name='password_reset'),
    path('api/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
      path(
        'auth/google/',
        GoogleAuthView.as_view(),
        name='google-auth'
    ),

    # 2) Callback Google (avec ?code=…) → renvoie { access_token, user }
    path(
        'auth/google/callback/',
        GoogleAuthView.as_view(),
        name='google-auth-callback'
    ),
    # Endpoints JWT
    # path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/register/', RegisterView.as_view(), name='register'),

    # Tes routes chat définies dans chat/urls.py
    path('api/chat/', include('chat.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


