"""Подписанная cookie: устройство уже открыло открытку с паролем — не спрашивать снова (долгий срок)."""
import hashlib

from django.conf import settings
from django.core import signing

SALT = "nfc.card.view_unlock.v1"
# «По максимуму»: 10 лет; cookie пересоздаётся при каждом успешном вводе пароля.
MAX_AGE = 60 * 60 * 24 * 365 * 10


def _cookie_name(card):
    key = f"{settings.SECRET_KEY}:{card.pk}:{card.token}"
    return "nfc_vu_" + hashlib.sha256(key.encode()).hexdigest()[:20]


def verify_unlock_cookie(request, card):
    raw = request.COOKIES.get(_cookie_name(card))
    if not raw:
        return False
    try:
        data = signing.loads(raw, salt=SALT, max_age=MAX_AGE)
    except Exception:
        return False
    try:
        cid = int(data.get("id", 0))
    except (TypeError, ValueError):
        return False
    return cid == card.pk and data.get("t") == card.token


def set_unlock_cookie(response, card):
    val = signing.dumps({"id": card.pk, "t": card.token}, salt=SALT)
    response.set_cookie(
        _cookie_name(card),
        val,
        max_age=MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=bool(getattr(settings, "SESSION_COOKIE_SECURE", False)),
    )
