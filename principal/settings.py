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


def _get_csv(name, default=""):
    return tuple(item.strip() for item in _get_env(name, default).split(",") if item.strip())


SECRET_KEY = _get_env("DJANGO_SECRET_KEY", required=True)
DEBUG = _get_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = [h.strip() for h in _get_env("DJANGO_ALLOWED_HOSTS", "").split(",") if h.strip()]
if "test" in sys.argv and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]
TRUSTED_PROXY_IPS = _get_csv("DJANGO_TRUSTED_PROXY_IPS", "127.0.0.1,::1")

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
    'api.middleware.RequestAuditLogMiddleware',
    'api.security.middleware.InternalWAFMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'api.middleware.SecurityHeadersMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'axes.middleware.AxesMiddleware',
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

CACHES = {
    "default": {
        "BACKEND": _get_env("DJANGO_CACHE_BACKEND", "django.core.cache.backends.locmem.LocMemCache"),
        "LOCATION": _get_env("DJANGO_CACHE_LOCATION", "geohabita-security-cache"),
        "TIMEOUT": int(_get_env("DJANGO_CACHE_TIMEOUT", "300")),
    }
}

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
        "map_public": _get_env("DRF_THROTTLE_MAP_PUBLIC", "180/minute"),
        "public_list": _get_env("DRF_THROTTLE_PUBLIC_LIST", "120/minute"),
        "upload_360": _get_env("DRF_THROTTLE_UPLOAD_360", "20/hour"),
        "plan_extraction": _get_env("DRF_THROTTLE_PLAN_EXTRACTION", "10/hour"),
        "register": _get_env("DRF_THROTTLE_REGISTER", "5/hour"),
        "recovery_request": _get_env("DRF_THROTTLE_RECOVERY_REQUEST", "5/hour"),
        "recovery_verify": _get_env("DRF_THROTTLE_RECOVERY_VERIFY", "15/hour"),
        "recovery_reset": _get_env("DRF_THROTTLE_RECOVERY_RESET", "8/hour"),
        "activation_resend": _get_env("DRF_THROTTLE_ACTIVATION_RESEND", "5/hour"),
        "frontend_error_report": _get_env("DRF_THROTTLE_FRONTEND_ERROR_REPORT", "30/minute"),
    },
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "EXCEPTION_HANDLER": "api.exception_handlers.safe_exception_handler",
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
MAX_IMAGE_PIXELS = int(_get_env("MAX_IMAGE_PIXELS", "40000000"))
MAX_360_UPLOAD_FILES = int(_get_env("MAX_360_UPLOAD_FILES", "20"))
MAX_360_UPLOAD_TOTAL_MB = int(_get_env("MAX_360_UPLOAD_TOTAL_MB", "80"))
MAX_360_CONNECTIONS_PER_REQUEST = int(_get_env("MAX_360_CONNECTIONS_PER_REQUEST", "200"))
MAX_PLAN_EXTRACTION_UPLOAD_MB = int(_get_env("MAX_PLAN_EXTRACTION_UPLOAD_MB", "15"))
ANTIVIRUS_ENABLED = _get_bool("ANTIVIRUS_ENABLED", False)
ANTIVIRUS_COMMAND = _get_env("ANTIVIRUS_COMMAND", "clamscan")
ANTIVIRUS_STRICT = _get_bool("ANTIVIRUS_STRICT", False)
DATA_UPLOAD_MAX_MEMORY_SIZE = int(_get_env("DATA_UPLOAD_MAX_MEMORY_SIZE", "10485760"))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(_get_env("FILE_UPLOAD_MAX_MEMORY_SIZE", "5242880"))
REGISTRATION_RESERVED_EMAIL_DOMAINS = tuple(_get_csv("REGISTRATION_RESERVED_EMAIL_DOMAINS", "geohabita.com"))
REGISTRATION_ALLOWED_INTERNAL_EMAILS = tuple(_get_csv("REGISTRATION_ALLOWED_INTERNAL_EMAILS", ""))

SECURITY_WAF = {
    "ENABLED": _get_bool("SECURITY_WAF_ENABLED", True),
    "VERSION": _get_env("SECURITY_WAF_VERSION", "waf-2026-05-29-response-observer-v2"),
    "WHITELIST_IPS": _get_csv("SECURITY_WAF_WHITELIST_IPS", "127.0.0.1,::1"),
    "API_PREFIXES": _get_csv("SECURITY_WAF_API_PREFIXES", "/api/"),
    "RATE_LIMIT_PER_MINUTE": int(_get_env("SECURITY_WAF_RATE_LIMIT_PER_MINUTE", "180")),
    "BURST_LIMIT_PER_10_SECONDS": int(_get_env("SECURITY_WAF_BURST_LIMIT_PER_10_SECONDS", "60")),
    "CONCURRENT_LIMIT": int(_get_env("SECURITY_WAF_CONCURRENT_LIMIT", "12")),
    "TEMP_BAN_MINUTES": int(_get_env("SECURITY_WAF_TEMP_BAN_MINUTES", "60")),
    "BAN_SCORE": int(_get_env("SECURITY_WAF_BAN_SCORE", "100")),
    "PERMANENT_SCORE": int(_get_env("SECURITY_WAF_PERMANENT_SCORE", "200")),
    "SENSITIVE_HITS_TO_BAN": int(_get_env("SECURITY_WAF_SENSITIVE_HITS_TO_BAN", "3")),
    "MISSING_HITS_TO_SCORE": int(_get_env("SECURITY_WAF_MISSING_HITS_TO_SCORE", "8")),
    "BODY_INSPECTION_BYTES": int(_get_env("SECURITY_WAF_BODY_INSPECTION_BYTES", "16384")),
    "LOG_SAMPLE_SECONDS": int(_get_env("SECURITY_WAF_LOG_SAMPLE_SECONDS", "60")),
    "BLOCK_NEGATIVE_CACHE_SECONDS": int(_get_env("SECURITY_WAF_BLOCK_NEGATIVE_CACHE_SECONDS", "120")),
    "BLOCK_POSITIVE_CACHE_SECONDS": int(_get_env("SECURITY_WAF_BLOCK_POSITIVE_CACHE_SECONDS", "60")),
    "CLEANUP_INTERVAL_SECONDS": int(_get_env("SECURITY_WAF_CLEANUP_INTERVAL_SECONDS", "86400")),
    "EVENT_RETENTION_DAYS": int(_get_env("SECURITY_WAF_EVENT_RETENTION_DAYS", "30")),
    "MAX_SECURITY_EVENTS": int(_get_env("SECURITY_WAF_MAX_SECURITY_EVENTS", "50000")),
    "CLEANUP_BATCH_SIZE": int(_get_env("SECURITY_WAF_CLEANUP_BATCH_SIZE", "1000")),
    "DEBUG_LOGS": _get_bool("SECURITY_WAF_DEBUG_LOGS", False),
    "WHITELIST_METHODS": _get_csv("SECURITY_WAF_WHITELIST_METHODS", "OPTIONS"),
    "WHITELIST_EXACT_PATHS": _get_csv(
        "SECURITY_WAF_WHITELIST_EXACT_PATHS",
        "/,/api/health/,/api/healthcheck/,/api/healthcheck,/api/security/waf-health/,/health/,/healthcheck/,/favicon.ico,/robots.txt",
    ),
    "WHITELIST_PATH_PREFIXES": _get_csv("SECURITY_WAF_WHITELIST_PATH_PREFIXES", "/static/,/media/"),
}

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
SHARE_FRONTEND_BASE_URL = _get_env(
    "SHARE_FRONTEND_BASE_URL",
    "https://www.geohabita.com",
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

TELEGRAM_ERROR_ALERTS_ENABLED = _get_bool("TELEGRAM_ERROR_ALERTS_ENABLED", False)
TELEGRAM_BOT_TOKEN = _get_env("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = _get_env("TELEGRAM_CHAT_ID", "")
TELEGRAM_SECURITY_ACTION_BASE_URL = _get_env("TELEGRAM_SECURITY_ACTION_BASE_URL", "")
TELEGRAM_SECURITY_ACTION_MAX_AGE_SECONDS = int(_get_env("TELEGRAM_SECURITY_ACTION_MAX_AGE_SECONDS", "86400"))
TELEGRAM_MANUAL_BLOCK_MINUTES = int(_get_env("TELEGRAM_MANUAL_BLOCK_MINUTES", "1440"))

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
        "api.error_reporting": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "api.security": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
