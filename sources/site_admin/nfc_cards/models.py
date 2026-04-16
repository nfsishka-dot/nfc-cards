import os
import secrets
import uuid
import logging
from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.db import models
from django.utils import timezone

log = logging.getLogger("nfc_cards")

def generate_token():
    return secrets.token_urlsafe(16)


def photo_upload_to(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        ext = ".jpg"
    return os.path.join("photos", instance.card.token, f"{secrets.token_hex(16)}{ext}")


def video_upload_to(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext not in {".mp4", ".webm", ".mov"}:
        ext = ".mp4"
    return os.path.join("videos", instance.card.token, f"{secrets.token_hex(16)}{ext}")


class LinkGroup(models.Model):
    """Пакет ссылок, созданный из админки (название + дата)."""

    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class Card(models.Model):
    token = models.CharField(max_length=64, unique=True, default=generate_token, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    link_group = models.ForeignKey(
        LinkGroup,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="cards",
    )

    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    background_color = models.CharField(max_length=7, default="#FFFFFF")
    text_color = models.CharField(max_length=7, default="#222222")

    title = models.CharField(max_length=255, blank=True)
    author_name = models.CharField(max_length=255, blank=True)
    content = models.TextField(blank=True)
    background = models.JSONField(default=dict, blank=True)

    external_images = models.JSONField(default=list, blank=True)
    external_videos = models.JSONField(default=list, blank=True)

    # Хэш пароля для просмотра опубликованной открытки (не для редактора). Пусто = без защиты.
    view_password_hash = models.CharField(max_length=128, blank=True, default="")
    # Зашифрованная копия для персонала (копирование в админке); пусто = нет резервной копии.
    view_password_cipher = models.TextField(blank=True, default="")

    total_size = models.BigIntegerField(default=0)

    def update_total_size(self):
        total = 0
        total += sum(self.photos.values_list("size", flat=True))
        total += sum(self.videos.values_list("size", flat=True))
        self.total_size = total
        self.save(update_fields=["total_size"])

    @property
    def total_size_mb(self):
        return round(self.total_size / (1024 * 1024), 2)

    def mark_published(self):
        self.is_published = True
        if not self.published_at:
            self.published_at = timezone.now()
        self.save(update_fields=["is_published", "published_at"])

    def clear_content(self):
        self.preview_drafts.all().delete()
        for p in self.photos.all().only("id", "file"):
            try:
                p.file.delete(save=False)
            except Exception:
                log.exception("clear_content photo delete failed card_id=%s photo_id=%s", self.id, p.id)
        for v in self.videos.all().only("id", "file"):
            try:
                v.file.delete(save=False)
            except Exception:
                log.exception("clear_content video delete failed card_id=%s video_id=%s", self.id, v.id)
        self.photos.all().delete()
        self.videos.all().delete()

        self.title = ""
        self.author_name = ""
        self.content = ""
        self.background = {}
        self.background_color = "#FFFFFF"
        self.external_images = []
        self.external_videos = []
        self.is_published = False
        self.published_at = None
        self.view_password_hash = ""
        self.view_password_cipher = ""
        self.total_size = 0
        self.save()

    @property
    def has_view_password(self) -> bool:
        return bool(self.view_password_hash)

    @property
    def can_reveal_view_password(self) -> bool:
        return bool(self.view_password_hash and self.view_password_cipher)

    def __str__(self):
        return f"Card {self.id} ({self.token})"


class PreviewDraft(models.Model):
    """Черновик preview: общее хранилище для всех воркеров, не in-memory."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name="preview_drafts")
    session_key = models.CharField(max_length=40, db_index=True)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["card", "session_key"]),
        ]


class Photo(models.Model):
    card = models.ForeignKey(Card, related_name="photos", on_delete=models.CASCADE)
    file = models.ImageField(upload_to=photo_upload_to)
    size = models.BigIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        old_size = int(self.size or 0)
        super().save(*args, **kwargs)
        if not self.file:
            return
        new_size = int(self.file.size or 0)
        if old_size != new_size:
            self.size = new_size
            super().save(update_fields=["size"])
        delta = new_size - old_size
        if delta:
            Card.objects.filter(id=self.card_id).update(total_size=F("total_size") + delta)

    def delete(self, *args, **kwargs):
        storage = self.file.storage
        name = self.file.name
        sz = int(self.size or 0)
        super().delete(*args, **kwargs)
        storage.delete(name)
        if sz:
            Card.objects.filter(id=self.card_id).update(
                total_size=Greatest(F("total_size") - sz, Value(0))
            )

    def __str__(self):
        return f"Photo for {self.card}"


class Video(models.Model):
    card = models.ForeignKey(Card, related_name="videos", on_delete=models.CASCADE)
    file = models.FileField(upload_to=video_upload_to)
    size = models.BigIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        old_size = int(self.size or 0)
        super().save(*args, **kwargs)
        if not self.file:
            return
        new_size = int(self.file.size or 0)
        if old_size != new_size:
            self.size = new_size
            super().save(update_fields=["size"])
        delta = new_size - old_size
        if delta:
            Card.objects.filter(id=self.card_id).update(total_size=F("total_size") + delta)

    def delete(self, *args, **kwargs):
        storage = self.file.storage
        name = self.file.name
        sz = int(self.size or 0)
        super().delete(*args, **kwargs)
        storage.delete(name)
        if sz:
            Card.objects.filter(id=self.card_id).update(
                total_size=Greatest(F("total_size") - sz, Value(0))
            )

    def __str__(self):
        return f"Video for {self.card}"

