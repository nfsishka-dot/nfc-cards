"""Кеш контекста публичного просмотра опубликованной открытки (GET /<token>/)."""
from __future__ import annotations

import hashlib
import json
import logging

from django.conf import settings
from django.core.cache import cache

from ..html_sanitize import sanitize_post_html
from . import backgrounds

log = logging.getLogger("nfc_cards")

_CACHE_PREFIX = "card_post"


def _cache_ttl() -> int:
    return int(getattr(settings, "CARD_POST_VIEW_CACHE_TTL", 300))


def _content_fingerprint(card) -> str:
    pub = card.published_at.isoformat() if card.published_at else ""
    parts = [
        card.title or "",
        card.content or "",
        json.dumps(card.background or {}, sort_keys=True, ensure_ascii=False),
        pub,
        card.view_password_hash or "",
    ]
    return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()[:32]


def cache_key_for_card_post(card) -> str:
    return f"{_CACHE_PREFIX}:{card.token}:{_content_fingerprint(card)}"


def build_post_template_context(card) -> dict:
    bg = backgrounds.normalize_background(
        card.background or {"type": "color", "value": card.background_color or "#ffffff"}
    )
    return {
        "title": card.title or "Открытка",
        "content": sanitize_post_html(card.content or ""),
        "background": bg,
        "background_url": backgrounds.background_media_url(bg),
    }


def get_or_build_post_context(card) -> dict:
    key = cache_key_for_card_post(card)
    cached = cache.get(key)
    if cached is not None:
        return dict(cached)
    ctx = build_post_template_context(card)
    try:
        cache.set(key, ctx, _cache_ttl())
    except Exception:
        log.exception("card_post cache set failed key=%s", key)
    return ctx


def invalidate_published_post_cache(card) -> None:
    key = cache_key_for_card_post(card)
    try:
        cache.delete(key)
    except Exception:
        log.exception("card_post cache delete failed key=%s", key)
