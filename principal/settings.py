"""
Django settings for principal project.
"""
import os
import sys
from datetime import timedelta
from pathlib import Path

import pymysql
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured

pymysql.install_as_MySQLdb()

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=True)

def _get_env(name, default=None, required=False):
    value = os.getenv(name, default)
    if required and (value is None or str(value).strip() == ""):
        if "test" in sys.argv:
            return f"test-{name.lower()}"
        raise ImproperlyConfigured(f"Missing required environment variable: {name}")
    return value


def _get_bool(name, default=False):
    return str(os.getenv(name, str(default))).strip().lower() in ("1", "true", "yes", "on")


SECRET_KEY = _get_env("DJANGO_SECRET_KEY", required=True)
DEBUG = _get_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = [h.strip() for h in _get_env("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
if "test" in sys.argv and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

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
    'axes',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
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
    'axes.middleware.AxesMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'api.middleware.RequestAuditLogMiddleware',
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
        'ENGINE': _get_env('DB_ENGINE', 'django.db.backends.mysql'),
        'NAME': _get_env('DB_NAME', required=True),
        'USER': _get_env('DB_USER', required=True),
        'PASSWORD': _get_env('DB_PASSWORD', required=True),
        'HOST': _get_env('DB_HOST', '127.0.0.1'),
        'PORT': _get_env('DB_PORT', '3306'),
        'OPTIONS': {
            'init_command': _get_env(
                'DB_INIT_COMMAND',
                "SET sql_mode='STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,"
                "ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION'"
            ),
        },
    }
}
if "test" in sys.argv:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",
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
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": _get_env("DRF_THROTTLE_ANON", "100/hour"),
        "user": _get_env("DRF_THROTTLE_USER", "1000/hour"),
        "login": _get_env("DRF_THROTTLE_LOGIN", "10/minute"),
        "refresh": _get_env("DRF_THROTTLE_REFRESH", "20/minute"),
        "clicks": _get_env("DRF_THROTTLE_CLICKS", "60/minute"),
        "register": _get_env("DRF_THROTTLE_REGISTER", "5/hour"),
        "recovery_request": _get_env("DRF_THROTTLE_RECOVERY_REQUEST", "5/hour"),
        "recovery_verify": _get_env("DRF_THROTTLE_RECOVERY_VERIFY", "15/hour"),
        "recovery_reset": _get_env("DRF_THROTTLE_RECOVERY_RESET", "8/hour"),
        "activation_resend": _get_env("DRF_THROTTLE_ACTIVATION_RESEND", "5/hour"),
    },
}

SIMPLE_JWT = {
    "USER_ID_FIELD": "idusuario",
    "USER_ID_CLAIM": "user_id",
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(_get_env("JWT_ACCESS_MINUTES", "30"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(_get_env("JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": _get_bool("JWT_ROTATE_REFRESH_TOKENS", True),
    "BLACKLIST_AFTER_ROTATION": _get_bool("JWT_BLACKLIST_AFTER_ROTATION", True),
    "UPDATE_LAST_LOGIN": _get_bool("JWT_UPDATE_LAST_LOGIN", True),
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
STATIC_ROOT = _get_env("DJANGO_STATIC_ROOT", str(BASE_DIR / "staticfiles"))

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# ============================================
# CORS
# ============================================
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [o.strip() for o in _get_env("DJANGO_CORS_ALLOWED_ORIGINS", "").split(",") if o.strip()]
CORS_ALLOW_CREDENTIALS = _get_bool("DJANGO_CORS_ALLOW_CREDENTIALS", False)

CSRF_TRUSTED_ORIGINS = [o.strip() for o in _get_env("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
]

AXES_ENABLED = _get_bool("AXES_ENABLED", True)
AXES_FAILURE_LIMIT = int(_get_env("AXES_FAILURE_LIMIT", "5"))
AXES_COOLOFF_TIME = int(_get_env("AXES_COOLOFF_HOURS", "1"))
AXES_LOCKOUT_PARAMETERS = ["ip_address", "username"]
AXES_USERNAME_FORM_FIELD = "correo"
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_CALLABLE = None
AXES_VERBOSE = _get_bool("AXES_VERBOSE", False)

# Security hardening for HTTPS deployments behind reverse proxy / cPanel.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = _get_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = _get_bool("DJANGO_SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = _get_bool("DJANGO_CSRF_COOKIE_SECURE", True)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = _get_env("DJANGO_SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = _get_env("DJANGO_CSRF_COOKIE_SAMESITE", "Lax")
SECURE_HSTS_SECONDS = int(_get_env("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = _get_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = _get_bool("DJANGO_SECURE_HSTS_PRELOAD", True)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = _get_env("DJANGO_SECURE_REFERRER_POLICY", "same-origin")

# Upload hardening
MAX_IMAGE_UPLOAD_MB = int(_get_env("MAX_IMAGE_UPLOAD_MB", "5"))
ANTIVIRUS_ENABLED = _get_bool("ANTIVIRUS_ENABLED", False)
ANTIVIRUS_COMMAND = _get_env("ANTIVIRUS_COMMAND", "clamscan")
ANTIVIRUS_STRICT = _get_bool("ANTIVIRUS_STRICT", False)
DATA_UPLOAD_MAX_MEMORY_SIZE = int(_get_env("DATA_UPLOAD_MAX_MEMORY_SIZE", "10485760"))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(_get_env("FILE_UPLOAD_MAX_MEMORY_SIZE", "5242880"))

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Recovery / mail settings
RECOVERY_CODE_TTL_MINUTES = int(_get_env("RECOVERY_CODE_TTL_MINUTES", "10"))
RECOVERY_CODE_MAX_ATTEMPTS = int(_get_env("RECOVERY_CODE_MAX_ATTEMPTS", "5"))
RECOVERY_CODE_COOLDOWN_SECONDS = int(_get_env("RECOVERY_CODE_COOLDOWN_SECONDS", "60"))
ACCOUNT_ACTIVATION_TTL_HOURS = int(_get_env("ACCOUNT_ACTIVATION_TTL_HOURS", "24"))
ACCOUNT_ACTIVATION_FRONTEND_URL = _get_env(
    "ACCOUNT_ACTIVATION_FRONTEND_URL",
    "https://www.geohabita.com/activar-cuenta",
)
ACCOUNT_PENDING_DELETE_DAYS = int(_get_env("ACCOUNT_PENDING_DELETE_DAYS", "7"))

EMAIL_BACKEND = _get_env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = _get_env("EMAIL_HOST", "")
EMAIL_PORT = int(_get_env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = _get_env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = _get_env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = _get_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = _get_bool("EMAIL_USE_SSL", False)
DEFAULT_FROM_EMAIL = _get_env("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "no-reply@geohabita.com")
EMAIL_TIMEOUT = int(_get_env("EMAIL_TIMEOUT", "20"))

# ============================================
# CLAVE PRIMARIA POR DEFECTO
# ============================================
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        }
    },
    "loggers": {
        "api.recovery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "api.audit": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
