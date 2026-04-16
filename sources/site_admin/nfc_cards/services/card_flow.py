"""Бизнес-логика редактора: preview, publish, save-draft, восстановление состояния."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from ..content_limits import human_error_message, validate_card_total_storage, validate_post_html
from ..html_sanitize import sanitize_post_html, sanitize_title
from ..models import Card
from .. import preview_store
from ..view_password_vault import encrypt_view_password
from . import backgrounds

log = logging.getLogger("nfc_cards")


def preview_session_key(token: str) -> str:
    return f"preview_id:{token}"


def build_editor_initial_state(request, card, token, restore_key: str | None) -> dict[str, Any]:
    """Собирает словарь editor_restore для шаблона редактора (как раньше в card_editor)."""
    editor_restore = None
    if restore_key:
        editor_restore = preview_store.pop_draft(restore_key, request, card.id)
    if editor_restore is None:
        bg = backgrounds.normalize_background(
            card.background or {"type": "color", "value": card.background_color or "#ffffff"}
        )
        editor_restore = {
            "title": sanitize_title(card.title or ""),
            "content": sanitize_post_html(card.content or ""),
            "background": bg,
            "background_value": json.dumps(bg, ensure_ascii=False),
        }

    editor_restore["content"] = sanitize_post_html(editor_restore.get("content") or "")
    editor_restore["title"] = sanitize_title(editor_restore.get("title") or "")

    editor_restore["background"] = backgrounds.normalize_background(editor_restore.get("background") or {})
    editor_restore["background_value"] = json.dumps(
        editor_restore["background"], ensure_ascii=False
    )
    return editor_restore


def editor_background_assets() -> list[dict[str, str]]:
    """Объекты {full, thumb} для редактора (см. backgrounds.list_background_images)."""
    return backgrounds.list_background_images()


def create_preview_draft(
    request,
    card: Card,
    token: str,
    content: str,
    title: str,
    background_raw: str,
) -> tuple[bool, str | None, str | None]:
    """
    Валидация + create_draft. Возвращает:
    (True, draft_id, None) при успехе;
    (False, None, error_code) — error_code для human_error_message.
    """
    background = backgrounds.parse_background(background_raw)

    err = validate_post_html(content)
    if err:
        log.warning("preview POST rejected token=%s code=%s", token, err)
        return False, None, err

    content_clean = sanitize_post_html(content)
    err = validate_post_html(content_clean)
    if err:
        log.warning("preview POST rejected after sanitize token=%s code=%s", token, err)
        return False, None, err

    err = validate_card_total_storage(card, content_clean, 0)
    if err:
        log.warning("preview POST rejected storage token=%s code=%s", token, err)
        return False, None, err

    payload = {
        "token": token,
        "content": content_clean,
        "title": sanitize_title(title),
        "background": background,
        "background_value": background_raw or json.dumps(background, ensure_ascii=False),
    }
    pid = preview_store.create_draft(request, card, payload)
    return True, pid, None


def load_preview_draft(request, card: Card, token: str) -> dict[str, Any] | None:
    """
    GET preview: либо None (нужен redirect на редактор),
    либо контекст для шаблона: card, content, background, background_url.
    """
    session_key = preview_session_key(token)
    pid = request.session.get(session_key)
    data = preview_store.get_draft(pid, request, card.id) if pid else None
    if not data or data.get("token") != token:
        return None
    background = backgrounds.normalize_background(data.get("background") or {})
    background_url = backgrounds.background_media_url(background)
    return {
        "card": card,
        "content": sanitize_post_html(data.get("content", "")),
        "background": background,
        "background_url": background_url,
    }


@dataclass(frozen=True)
class FinalizeOutcome:
    redirect_name: str
    success_message: str | None = None
    error_human_code: str | None = None
    error_literal: str | None = None


def publish_card_from_preview(request, card: Card, token: str) -> FinalizeOutcome:
    """Публикация из preview-сессии (логика card_finalize)."""
    session_key = preview_session_key(token)
    pid = request.session.get(session_key)
    if not pid:
        request.session.pop(session_key, None)
        return FinalizeOutcome(redirect_name="card_editor")

    # Читаем payload для валидации (без удаления). Финальное чтение и удаление — под lock в транзакции ниже.
    data_for_validate = preview_store.get_draft(pid, request, card.id)
    if not data_for_validate:
        request.session.pop(session_key, None)
        return FinalizeOutcome(redirect_name="card_editor")

    content = sanitize_post_html(data_for_validate.get("content") or "")
    title = sanitize_title(data_for_validate.get("title") or "")

    err = validate_post_html(content)
    if err:
        log.warning("finalize rejected token=%s code=%s", token, err)
        return FinalizeOutcome(redirect_name="card_preview", error_human_code=err)

    err = validate_card_total_storage(card, content, 0)
    if err:
        log.warning("finalize rejected storage token=%s code=%s", token, err)
        return FinalizeOutcome(redirect_name="card_preview", error_human_code=err)

    use_pw = request.POST.get("use_view_password") == "1"
    pw = request.POST.get("view_password") or ""
    pw2 = request.POST.get("view_password_confirm") or ""
    if use_pw:
        if not pw:
            return FinalizeOutcome(
                redirect_name="card_preview",
                error_literal="Пароль на просмотр: введите непустой пароль.",
            )
        if len(pw) > 128:
            return FinalizeOutcome(
                redirect_name="card_preview",
                error_literal="Пароль слишком длинный.",
            )
        if pw != pw2:
            return FinalizeOutcome(
                redirect_name="card_preview",
                error_literal="Пароли не совпадают.",
            )

    try:
        with transaction.atomic():
            d = preview_store.lock_draft(pid, request, card.id)
            if not d:
                return FinalizeOutcome(redirect_name="card_editor")

            payload = d.payload or {}
            card.title = title
            card.content = content
            card.background = backgrounds.normalize_background(payload.get("background") or {})
            if card.background.get("type") == "color":
                card.background_color = card.background.get("value", "#ffffff")
            card.is_published = True
            card.published_at = timezone.now()
            if use_pw:
                card.view_password_hash = make_password(pw)
                card.view_password_cipher = encrypt_view_password(pw)
            else:
                card.view_password_hash = ""
                card.view_password_cipher = ""

            card.save(
                update_fields=[
                    "title",
                    "content",
                    "background",
                    "background_color",
                    "view_password_hash",
                    "view_password_cipher",
                    "is_published",
                    "published_at",
                ]
            )
            # Важно: удаляем draft только после успешного сохранения Card.
            d.delete()
    except Exception:
        log.exception("finalize save failed token=%s", token)
        return FinalizeOutcome(
            redirect_name="card_preview",
            error_literal="Не удалось сохранить открытку. Попробуйте снова.",
        )

    request.session.pop(session_key, None)

    return FinalizeOutcome(
        redirect_name="card_entry",
        success_message="Открытка опубликована.",
    )


def restore_preview_to_editor(request, card: Card, token: str) -> str | None:
    """
    Возвращает restore-id для query string или None, если редирект на /edit/ без параметра.
    """
    session_key = preview_session_key(token)
    pid = request.session.pop(session_key, None)
    data = preview_store.pop_draft(pid, request, card.id) if pid else None
    if not data:
        return None
    rid = preview_store.create_draft(request, card, data)
    return rid


def save_card_draft_response(request, card: Card, token: str) -> tuple[int, dict[str, Any]]:
    """
    Полный цикл save-draft: валидация + запись Card.
    Возвращает (status_code, body) для JsonResponse(..., status=...).
    """
    if card.is_published:
        return 403, {"ok": False, "error": "published"}

    content = request.POST.get("content") or ""
    title = request.POST.get("title") or ""
    background_raw = request.POST.get("background_value") or ""
    background = backgrounds.parse_background(background_raw)

    err = validate_post_html(content)
    if err:
        return 400, {"ok": False, "errors": {"_html": human_error_message(err)}}

    content_clean = sanitize_post_html(content)
    err = validate_post_html(content_clean)
    if err:
        return 400, {"ok": False, "errors": {"_html": human_error_message(err)}}

    err = validate_card_total_storage(card, content_clean, 0)
    if err:
        return 400, {"ok": False, "errors": {"_html": human_error_message(err)}}

    use_pw = request.POST.get("use_view_password") == "1"
    pw = request.POST.get("view_password") or ""
    pw2 = request.POST.get("view_password_confirm") or ""
    errors: dict[str, str] = {}
    if use_pw:
        if not pw:
            errors["view_password"] = "Введите пароль (от 1 символа)."
        if len(pw) > 128:
            errors["view_password"] = "Пароль слишком длинный."
        if pw != pw2:
            errors["view_password_confirm"] = "Пароли не совпадают."
    if errors:
        return 400, {"ok": False, "errors": errors}

    card.title = sanitize_title(title)
    card.content = content_clean
    card.background = background
    if card.background.get("type") == "color":
        card.background_color = card.background.get("value", "#ffffff")

    if use_pw:
        card.view_password_hash = make_password(pw)
        card.view_password_cipher = encrypt_view_password(pw)
    else:
        card.view_password_hash = ""
        card.view_password_cipher = ""

    update_fields = [
        "title",
        "content",
        "background",
        "background_color",
        "view_password_hash",
        "view_password_cipher",
    ]
    try:
        card.save(update_fields=update_fields)
    except Exception:
        log.exception("save_draft failed token=%s", token)
        return 500, {"ok": False, "errors": {"_html": "Не удалось сохранить. Попробуйте снова."}}

    return 200, {"ok": True, "has_view_password": bool(card.view_password_hash)}
