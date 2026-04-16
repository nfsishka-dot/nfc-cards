"""Шифрованная копия пароля просмотра для персонала (расшифровка только с SECRET_KEY).

cryptography импортируется лениво: без пакета Django всё равно стартует, пароль по хэшу работает,
копирование в админке — после pip install cryptography.
"""
import base64
import hashlib
import logging

from django.conf import settings

log = logging.getLogger("nfc_cards")


def is_vault_available() -> bool:
    try:
        import cryptography.fernet  # noqa: F401
        return True
    except ImportError:
        return False


def _fernet():
    from cryptography.fernet import Fernet

    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_view_password(plain: str) -> str:
    if not plain:
        return ""
    try:
        return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")
    except ImportError:
        log.warning(
            "cryptography не установлен — view_password_cipher не сохранён. "
            "Выполните: pip install cryptography"
        )
        return ""
    except Exception:
        log.exception("encrypt_view_password failed")
        return ""


def decrypt_view_password(token: str) -> str:
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
