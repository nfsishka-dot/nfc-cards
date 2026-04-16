import secrets
from django.db import models


def generate_hashcode() -> str:
    # Достаточно длинный токен, похожий на API‑ключ
    return secrets.token_urlsafe(16)


def generate_edit_token() -> str:
    return secrets.token_urlsafe(32)


class Note(models.Model):
    hashcode = models.CharField(max_length=64, unique=True, db_index=True, default=generate_hashcode)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    edit_token = models.CharField(max_length=128, default=generate_edit_token)

    def __str__(self) -> str:
        return f"Note {self.hashcode}"

