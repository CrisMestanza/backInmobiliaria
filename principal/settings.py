"""
Django settings for principal project.
"""
import pymysql
pymysql.install_as_MySQLdb()

from pathlib import Path
from datetime import timedelta
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-ov++q_s+vs)5(8lmp)4g=*#v&nfrxk=x@j+u=j8&*lj-sr0ek3'
DEBUG = True

ALLOWED_HOSTS = [
    'api.geohabita.com',
    'www.api.geohabita.com',
    'geohabita.com',   # agrega también tu front
    'www.geohabita.com'
]

# ============================================
# APLICACIONES
# ============================================
INSTALLED_APPS = [
    'django.contrib.admin', 
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework_simplejwt',
    "rest_framework",
    'api',
]

# ============================================
# MIDDLEWARE
# ============================================
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'principal.urls'

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

WSGI_APPLICATION = 'principal.wsgi.application'

# ============================================
# BASE DE DATOS
# ============================================
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql',
        'NAME': 'geohzdwu_inmobiliaria',
        'USER': 'geohzdwu_mestanza',
        'PASSWORD': '72655883Cristian#',
        'HOST': '127.0.0.1',
        'PORT': '3306',
    }
}

AUTH_USER_MODEL = 'api.Usuario'

# ============================================
# REST FRAMEWORK / JWT
# ============================================
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "api.authentication.CustomJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "USER_ID_FIELD": "idusuario",
    "USER_ID_CLAIM": "user_id",
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=5),
}

# ============================================
# INTERNACIONALIZACIÓN
# ============================================
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ============================================
# ARCHIVOS ESTÁTICOS Y MEDIA
# ============================================
STATIC_URL = 'static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ============================================
# CORS
# ============================================
CORS_ALLOW_ALL_ORIGINS = True   # permite acceso desde cualquier origen
CORS_ALLOW_CREDENTIALS = True   #  habilita cookies o headers

# ============================================
# CLAVE PRIMARIA POR DEFECTO
# ============================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
