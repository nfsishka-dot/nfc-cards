from pathlib import Path
import ipaddress
import os
from typing import Tuple, Union

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

"""
Production-safe defaults (fail-fast):
- DEBUG по умолчанию выключен.
- Включайте DEBUG только явно через DJANGO_DEBUG=1/true/yes.
Это защищает от случайного запуска production с DEBUG=True.
"""
DEBUG = os.environ.get("DJANGO_DEBUG", "").lower() in ("1", "true", "yes")

# PRODUCTION: задайте DJANGO_SECRET_KEY непустой строкой (не "change-me-in-production").
# Генерация: python -c "import secrets; print(secrets.token_urlsafe(64))"
# При DEBUG=0 сервер не стартует с дефолтным ключом (проверка ниже, ~строка 300).
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "change-me-in-production")

_raw_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "").strip()
if _raw_hosts:
    ALLOWED_HOSTS = [h.strip() for h in _raw_hosts.split(",") if h.strip()]
elif DEBUG:
    ALLOWED_HOSTS = ["*"]
else:
    ALLOWED_HOSTS = []

_origins = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").strip()
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _origins.split(",") if o.strip()]

# В DEBUG добавляем http://<LAN-IP>:порт для телефона в той же Wi‑Fi (Django 4+ CSRF по Origin).
if DEBUG:
    _dev_port = os.environ.get("DJANGO_DEV_PORT", "8000").strip() or "8000"
    _csrf_dev = [
        f"http://127.0.0.1:{_dev_port}",
        f"http://localhost:{_dev_port}",
    ]
    try:
        import socket

        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.3)
        s.connect(("8.8.8.8", 80))
        _lan = s.getsockname()[0]
        s.close()
        if not _lan.startswith("127.") and not _lan.startswith("198.18."):
            _csrf_dev.append(f"http://{_lan}:{_dev_port}")
    except Exception:
        pass
    try:
        import socket

        _hn = socket.gethostname()
        for _lan in socket.gethostbyname_ex(_hn)[2]:
            if _lan.startswith("127.") or _lan.startswith("198.18."):
                continue
            if (
                _lan.startswith("192.168.")
                or _lan.startswith("10.")
                or _lan.startswith("172.16.")
                or _lan.startswith("172.17.")
                or _lan.startswith("172.18.")
                or _lan.startswith("172.19.")
                or _lan.startswith("172.2")
                or _lan.startswith("172.30.")
                or _lan.startswith("172.31.")
            ):
                _o = f"http://{_lan}:{_dev_port}"
                if _o not in _csrf_dev:
                    _csrf_dev.append(_o)
    except Exception:
        pass
    for _o in _csrf_dev:
        if _o not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(_o)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "nfc_cards.apps.NfcCardsConfig",
    "tapnote",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "nfc_cards.middleware.CardEditorRateLimitMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "nfc_site.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "nfc_cards" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "nfc_site.wsgi.application"
ASGI_APPLICATION = "nfc_site.asgi.application"

_database_url = os.environ.get("DATABASE_URL", "").strip()
if _database_url:
    DATABASES = {
        "default": dj_database_url.parse(
            _database_url,
            conn_max_age=int(os.environ.get("DATABASE_CONN_MAX_AGE", "600")),
            ssl_require=os.environ.get("DATABASE_SSL_REQUIRE", "").lower()
            in ("1", "true", "yes"),
        )
    }
elif DEBUG:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    raise ImproperlyConfigured(
        "Для production (DEBUG=0) задайте DATABASE_URL (PostgreSQL). "
        "Локально с SQLite оставьте DEBUG=1 или задайте DATABASE_URL."
    )

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "ru-ru"

TIME_ZONE = "Europe/Moscow"

USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

if not DEBUG:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Иначе @login_required ведёт на несуществующий /accounts/login/ — панель «ломается»
LOGIN_URL = "nfc_cards:login"

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = "info@example.com"
ADMIN_CONTACT_EMAIL = "info@example.com"

SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = os.environ.get("DJANGO_SESSION_COOKIE_SECURE", "").lower() in ("1", "true", "yes")
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "").lower() in ("1", "true", "yes")
# Только если за nginx/балансером, который честно выставляет X-Forwarded-Proto (иначе заголовок можно подделать).
if os.environ.get("DJANGO_TRUST_FORWARDED_PROTO", "").lower() in ("1", "true", "yes"):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
else:
    SECURE_PROXY_SSL_HEADER = None

# MEDIA serving:
#   Вариант A (маленький трафик / staging):  DJANGO_SERVE_MEDIA=1  — Django отдаёт /media/ сам.
#   Вариант B (production, рекомендуется):   nginx location /media/ { alias /app/media/; }
#   Без одного из вариантов загруженные фото будут отдавать 404 в проде.
SERVE_MEDIA = os.environ.get("DJANGO_SERVE_MEDIA", "").lower() in ("1", "true", "yes")

# Загрузки редактора и тяжёлые POST preview (legacy base64)
DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DJANGO_DATA_UPLOAD_MAX_MEMORY", str(30 * 1024 * 1024)))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DJANGO_FILE_UPLOAD_MAX_MEMORY", str(25 * 1024 * 1024)))
EDITOR_IMAGE_MAX_BYTES = int(os.environ.get("DJANGO_EDITOR_IMAGE_MAX_BYTES", str(10 * 1024 * 1024)))
EDITOR_IMAGE_MAX_PIXELS = int(os.environ.get("DJANGO_EDITOR_IMAGE_MAX_PIXELS", str(24_000_000)))
EDITOR_IMAGE_HARD_MAX_PIXELS = int(os.environ.get("DJANGO_EDITOR_IMAGE_HARD_MAX_PIXELS", str(80_000_000)))
EDITOR_IMAGE_MAX_EDGE = int(os.environ.get("DJANGO_EDITOR_IMAGE_MAX_EDGE", "1920"))

POST_HTML_MAX_BYTES = int(os.environ.get("DJANGO_POST_HTML_MAX_BYTES", str(1_048_576)))
POST_TEXT_MAX_CHARS = int(os.environ.get("DJANGO_POST_TEXT_MAX_CHARS", "10000"))
POST_MAX_IMAGES = int(os.environ.get("DJANGO_POST_MAX_IMAGES", "25"))
CARD_MAX_TOTAL_BYTES = int(os.environ.get("DJANGO_CARD_MAX_TOTAL_BYTES", str(50 * 1024 * 1024)))

RATE_LIMIT_PER_MINUTE = int(os.environ.get("DJANGO_RATE_LIMIT_PER_MINUTE", "25"))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("DJANGO_RATE_LIMIT_WINDOW_SECONDS", "60"))
ADMIN_LOGIN_RATE_LIMIT_PER_MINUTE = int(os.environ.get("DJANGO_ADMIN_LOGIN_RATE_LIMIT", "25"))


def _trusted_proxy_networks() -> Tuple[Union[ipaddress.IPv4Network, ipaddress.IPv6Network], ...]:
    """CIDR через запятую: только если REMOTE_ADDR попадает в эту сеть, доверяем X-Forwarded-For."""
    raw = os.environ.get("DJANGO_TRUSTED_PROXY_CIDRS", "").strip()
    if not raw:
        return tuple()
    out: list[Union[ipaddress.IPv4Network, ipaddress.IPv6Network]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.append(ipaddress.ip_network(part, strict=False))
        except ValueError:
            continue
    return tuple(out)


TRUSTED_PROXY_NETWORKS = _trusted_proxy_networks()

PREVIEW_DRAFT_MAX_AGE_HOURS = int(os.environ.get("DJANGO_PREVIEW_DRAFT_MAX_AGE_HOURS", "2"))

# Публичный просмотр опубликованной открытки (card_entry), секунды
CARD_POST_VIEW_CACHE_TTL = int(os.environ.get("DJANGO_CARD_POST_VIEW_CACHE_TTL", "300"))

_redis_url = os.environ.get("REDIS_URL", "").strip()
if _redis_url:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
            "KEY_PREFIX": "nfc",
            "TIMEOUT": 300,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "nfc-unified-locmem",
        }
    }

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "std": {
            "format": "%(levelname)s %(asctime)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "std",
        },
    },
    "loggers": {
        "nfc_cards": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "nfc_cards.ratelimit": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "nfc_cards.audit": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# --- Production hardening (не ломает локальную разработку и pytest) ---
DJANGO_PRODUCTION = os.environ.get("DJANGO_PRODUCTION", "").lower() in ("1", "true", "yes")
if DJANGO_PRODUCTION:
    DEBUG = False

if not DEBUG:
    if not SECRET_KEY or str(SECRET_KEY).strip() == "change-me-in-production":
        raise ImproperlyConfigured(
            "Небезопасная конфигурация: DEBUG=0 требует непустой DJANGO_SECRET_KEY "
            "(и он не должен быть равен 'change-me-in-production')."
        )
    if not ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            "Небезопасная конфигурация: DEBUG=0 требует непустой DJANGO_ALLOWED_HOSTS "
            "(список доменов через запятую)."
        )

if DJANGO_PRODUCTION and not _redis_url:
    raise ImproperlyConfigured(
        "DJANGO_PRODUCTION=1: задайте REDIS_URL (кеш публичного поста + rate limit между воркерами)."
    )
