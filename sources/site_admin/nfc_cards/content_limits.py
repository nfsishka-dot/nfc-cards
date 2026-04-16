"""Лимиты размера контента открытки (без изменения UI — ошибки через messages / JSON)."""
from __future__ import annotations

import re

from django.conf import settings
from django.utils.html import strip_tags


def _html_bytes(html: str) -> int:
    return len((html or "").encode("utf-8"))


def count_img_tags(html: str) -> int:
    return len(re.findall(r"<img\b", html or "", re.I))


def visible_text_length(html: str) -> int:
    return len((strip_tags(html or "") or "").strip())


def validate_post_html(html: str) -> str | None:
    """
    Возвращает код ошибки или None, если ок.
    Проверка до/после sanitize — вызывать для сырого и очищенного при необходимости.

    Лимиты:
      POST_HTML_MAX_BYTES  (1 MB по умолчанию) — размер HTML-текста (без медиафайлов).
        Нормальная открытка с 25 картинками по ~100 символов URL занимает ~5 KB.
        1 MB — запас >200x относительно реального максимума. Намеренно ниже 12 MB
        лимита legacy data:image/ в sanitizer: даже если бы base64 прошёл sanitize,
        validate отловил бы его здесь (но первым стоит явная проверка на "data:image/").
      CARD_MAX_TOTAL_BYTES (50 MB по умолчанию) — суммарный размер HTML + медиафайлов.
    """
    # Единый потолок: HTML не может быть больше общего лимита карточки.
    max_total = getattr(settings, "CARD_MAX_TOTAL_BYTES", 50 * 1024 * 1024)
    max_html = min(getattr(settings, "POST_HTML_MAX_BYTES", max_total), max_total)
    max_text = getattr(settings, "POST_TEXT_MAX_CHARS", 10_000)
    max_img = getattr(settings, "POST_MAX_IMAGES", 25)

    # Inline-картинки (data:/blob:) запрещены: они раздувают HTML и не персистятся как медиа-файлы.
    # Все изображения должны быть загружены и представлены URL.
    low = (html or "").lower()
    if "data:image/" in low or "blob:" in low:
        return "inline_images_not_allowed"

    if _html_bytes(html) > max_html:
        return "html_too_large"
    if visible_text_length(html) > max_text:
        return "text_too_long"
    if count_img_tags(html) > max_img:
        return "too_many_images"
    return None


def validate_card_total_storage(card, html: str, extra_media_bytes: int = 0) -> str | None:
    """Сумма: размер HTML + total_size карточки (фото/видео) + доп. байты (новая загрузка)."""
    max_total = getattr(settings, "CARD_MAX_TOTAL_BYTES", 50 * 1024 * 1024)
    content_b = _html_bytes(html or "")
    media = int(card.total_size or 0) + int(extra_media_bytes)
    if content_b + media > max_total:
        return "card_too_large"
    return None


def human_error_message(code: str) -> str:
    return {
        "inline_images_not_allowed": "Вставка изображений как data:/blob: запрещена. Вставьте картинку ещё раз — редактор загрузит её как файл.",
        "html_too_large": "Слишком большой объём HTML. Сократите текст или уменьшите число вставок.",
        "text_too_long": "Текст открытки превышает 10 000 символов.",
        "too_many_images": "Не более 25 изображений в одной открытке.",
        "card_too_large": "Общий размер открытки (текст и файлы) не может превышать 50 МБ.",
    }.get(code, "Ограничение контента.")
