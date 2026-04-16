"""Хранение черновиков preview в БД (multi-worker, переживает рестарт)."""
from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Card, PreviewDraft


def ensure_session_key(request) -> str:
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def create_draft(request, card: Card, payload: dict[str, Any]) -> str:
    sk = ensure_session_key(request)
    hours = int(getattr(settings, "PREVIEW_DRAFT_MAX_AGE_HOURS", 2))
    # Под нагрузкой синхронная очистка на каждый preview POST создаёт тяжёлые DELETE/locks.
    # Чистим вероятностно (и всегда можно запускать management command cleanup_preview_drafts по cron).
    cleanup_prob = float(getattr(settings, "PREVIEW_DRAFT_CLEANUP_PROBABILITY", 0.01))
    if cleanup_prob > 0 and random.random() < cleanup_prob:
        PreviewDraft.objects.filter(
            created_at__lt=timezone.now() - timedelta(hours=hours)
        ).delete()
    draft = PreviewDraft.objects.create(card=card, session_key=sk, payload=payload)
    return str(draft.id)


def get_draft(draft_id: str, request, card_id: int) -> dict[str, Any] | None:
    if not draft_id:
        return None
    ensure_session_key(request)
    try:
        d = PreviewDraft.objects.get(
            id=draft_id,
            card_id=card_id,
            session_key=request.session.session_key,
        )
    except (PreviewDraft.DoesNotExist, ValueError):
        return None
    return d.payload


@transaction.atomic
def pop_draft(draft_id: str, request, card_id: int) -> dict[str, Any] | None:
    if not draft_id:
        return None
    ensure_session_key(request)
    try:
        d = PreviewDraft.objects.select_for_update().get(
            id=draft_id,
            card_id=card_id,
            session_key=request.session.session_key,
        )
    except (PreviewDraft.DoesNotExist, ValueError):
        return None
    data = d.payload
    d.delete()
    return data


def lock_draft(draft_id: str, request, card_id: int) -> PreviewDraft | None:
    """
    Возвращает PreviewDraft под row lock (select_for_update) внутри транзакции.
    Важно для publish: удаляем draft только после успешного сохранения Card,
    иначе при сбое БД/сервера можно потерять данные пользователя.
    """
    if not draft_id:
        return None
    ensure_session_key(request)
    try:
        return (
            PreviewDraft.objects.select_for_update()
            .select_related(None)
            .get(id=draft_id, card_id=card_id, session_key=request.session.session_key)
        )
    except (PreviewDraft.DoesNotExist, ValueError):
        return None
