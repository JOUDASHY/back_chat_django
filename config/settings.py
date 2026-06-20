from pathlib import Path
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import timedelta


# Build paths inside the project like this: BASE_DIR / 'subdir'.

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')
# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/


# 4) Clés Pusher lues depuis l’environnement
PUSHER_APP_ID  = os.getenv('PUSHER_APP_ID')
PUSHER_KEY     = os.getenv('PUSHER_KEY')
PUSHER_SECRET  = os.getenv('PUSHER_SECRET')
PUSHER_CLUSTER = os.getenv('PUSHER_CLUSTER')
FRONTEND_URL = os.getenv('FRONTEND_URL')

# LiveKit (appels audio/vidéo self-hosted)
LIVEKIT_URL = os.getenv('LIVEKIT_URL', '')
LIVEKIT_API_KEY = os.getenv('LIVEKIT_API_KEY', '')
LIVEKIT_API_SECRET = os.getenv('LIVEKIT_API_SECRET', '')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'django-insecure-^f*&ik!m%v7mf=p%xr#%lrfsrg82ek##153*8d7=p70)n8&n5x')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Update ALLOWED_HOSTS
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    # Third-party
    'rest_framework',
    'rest_framework.authtoken',  # Add this line
    'rest_framework_simplejwt',
    'corsheaders',
    'channels',
    # allauth
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    # Local
    'chat',
]
# Session
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_COOKIE_AGE = 1800  # 30 minutes
SESSION_COOKIE_SECURE = True  # True en production
SESSION_COOKIE_SAMESITE = 'Lax'  # Pour les API cross-domain

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',  # MUST BE FIRST
    'django.middleware.security.SecurityMiddleware',
    # 'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    # Default Django middleware
    'django.contrib.sessions.middleware.SessionMiddleware',
     'allauth.account.middleware.AccountMiddleware',  # Ajoutez cette ligne
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases


# Configuration de la base de données
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': os.getenv('DB_NAME'),
        'USER': os.getenv('DB_USER'),
        'PASSWORD': os.getenv('DB_PASSWORD'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '3306'),
        'OPTIONS': {
            'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),    # ou ce qui te convient
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    # … autres réglages …
}

# CORS settings
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False

def _split_env_list(key: str) -> list[str]:
    return [v.strip() for v in os.getenv(key, '').split(',') if v.strip()]


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        normalized = item.rstrip('/')
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


BACKEND_URL = os.getenv('BACKEND_URL')
FRONTEND_URL = os.getenv('FRONTEND_URL')

CORS_ALLOWED_ORIGINS = _dedupe(
    _split_env_list('CORS_ALLOWED_ORIGINS')
    + ([FRONTEND_URL] if FRONTEND_URL else [])
    + ([BACKEND_URL] if BACKEND_URL else [])
)

CSRF_TRUSTED_ORIGINS = _dedupe(
    _split_env_list('CSRF_TRUSTED_ORIGINS') + CORS_ALLOWED_ORIGINS
)

CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
    'access-control-allow-credentials',
]

CORS_EXPOSE_HEADERS = ['content-type', 'x-csrftoken']

# Media settings
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Security settings
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
CSRF_COOKIE_HTTPONLY = False  # Permettre l'accès JS au cookie CSRF

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'django.contrib.staticfiles.storage.StaticFilesStorage'  # Change this line

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Get host from URL
def get_hosts_from_urls():
    hosts = set()
    for url in [FRONTEND_URL or '', BACKEND_URL or '']:
        if url:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.netloc:
                hosts.add(parsed.netloc.split(':')[0])
    return list(hosts)

# Combine explicit ALLOWED_HOSTS with hosts from URLs
ALLOWED_HOSTS = _split_env_list('ALLOWED_HOSTS') + get_hosts_from_urls()
ALLOWED_HOSTS = _dedupe(ALLOWED_HOSTS)

# Django REST Framework and JWT configuration
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'chat.authentication.ActiveJWTAuthentication',
    ),
}

# Optional: configure Simple JWT token lifetimes
from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'AUTH_HEADER_TYPES': ('Bearer',),
}

# Environment settings
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'

# Security settings - only enable SSL redirect in production
SECURE_SSL_REDIRECT = (
    os.getenv('SECURE_SSL_REDIRECT', 'False').lower() == 'true' 
    and ENVIRONMENT == 'production'
)
CSRF_COOKIE_SECURE = (
    os.getenv('CSRF_COOKIE_SECURE', 'False').lower() == 'true'
    and ENVIRONMENT == 'production'
)
SESSION_COOKIE_SECURE = (
    os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'
    and ENVIRONMENT == 'production'
)

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

SITE_ID = 1

LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/'

# Paramètres facultatifs pour personnaliser le comportement de allauth
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.getenv('GOOGLE_CLIENT_ID'),
            'secret': os.getenv('GOOGLE_CLIENT_SECRET'),
            'key': ''
        },
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        }
    }
}

EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST=os.environ.get('EMAIL_HOST')
EMAIL_USE_TLS= os.environ.get('EMAIL_USE_TLS')
EMAIL_PORT=  os.environ.get('EMAIL_PORT')
EMAIL_HOST_USER=os.environ.get('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD=os.environ.get('EMAIL_HOST_PASSWORD')
EMAIL_USE_TLS =  os.environ.get('EMAIL_USE_TLS')

# Redis Configuration
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))
REDIS_DB = int(os.getenv('REDIS_DB', 0))

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}',
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
            'SOCKET_CONNECT_TIMEOUT': 5,
            'SOCKET_TIMEOUT': 5,
        }
    }
}

# Channels configuration with Redis
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [f'redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}'],
        },
    },
}

# Use Redis for session backend
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"
DATA_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024 * 1024  # 2GB

print(f"Redis Host: {REDIS_HOST}")
print(f"Redis Port: {REDIS_PORT}")
print(f"Redis DB: {REDIS_DB}")
