"""Санитизация HTML контента открытки (bleach + CSS)."""
from __future__ import annotations

import re

import bleach
from bleach.css_sanitizer import CSSSanitizer

# Quill + выравнивание картинок используют div/span и классы ql-*
_ALLOWED_TAGS = frozenset(
    {
        "p",
        "br",
        "strong",
        "b",
        "em",
        "i",
        "u",
        "s",
        "a",
        "img",
        "ul",
        "ol",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "span",
        "div",
    }
)

# Стили, нужные для Quill (цвета, шрифты) и resize/align изображений
_ALLOWED_CSS_PROPERTIES = frozenset(
    {
        "color",
        "background-color",
        "font-size",
        "font-family",
        "font-weight",
        "font-style",
        "text-align",
        "line-height",
        "width",
        "height",
        "max-width",
        "max-height",
        "min-width",
        "min-height",
        "float",
        "display",
        "margin",
        "margin-left",
        "margin-right",
        "margin-top",
        "margin-bottom",
        "padding",
        "padding-left",
        "padding-right",
        "border",
        "border-radius",
        "box-sizing",
        "vertical-align",
        "white-space",
        "object-fit",
        "text-decoration",
        "text-decoration-line",
        "text-decoration-style",
        "text-decoration-color",
        "letter-spacing",
        "word-break",
        "overflow-wrap",
    }
)

# TECH DEBT: _safe_img_src допускает data:image/ base64 через sanitize для совместимости
# со старыми открытками, созданными до внедрения upload-image пайплайна.
# Проверка БД (2026-04): ни одна из 1215 открыток не содержит data:image/ в content.
# validate_post_html() жёстко блокирует data:image/ при save/preview/publish — это
# основной барьер. Sanitize — только вторичный слой отображения.
#
# POST-DEPLOY CLEANUP: после подтверждения отсутствия data:image/ в проде-БД
# можно убрать ветку data:image/ из _safe_img_src полностью и удалить _MAX_DATA_IMAGE_LEN.
# Миграция данных не нужна — контента с base64 нет.
_MAX_DATA_IMAGE_LEN = 12_000_000  # legacy compat, см. комментарий выше

_css_sanitizer = CSSSanitizer(allowed_css_properties=list(_ALLOWED_CSS_PROPERTIES))


def _safe_img_src(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return False
    if v.startswith(("http://", "https://", "/")):
        return True
    # TECH DEBT: data:image/ разрешён здесь только для обратной совместимости (legacy).
    # В новом контенте data:image/ не должно быть: validate_post_html() отклоняет его
    # на уровне save/preview/publish. Удалить этот блок после POST-DEPLOY CLEANUP выше.
    if v.startswith("data:image/"):
        if ";base64," not in v:
            return False
        mime = v.split(";", 1)[0].lower()
        if mime not in (
            "data:image/jpeg",
            "data:image/jpg",
            "data:image/png",
            "data:image/webp",
            "data:image/gif",
        ):
            return False
        return len(v) <= _MAX_DATA_IMAGE_LEN
    return False


def _attr(tag: str, name: str, value: str) -> bool:
    n = name.lower()
    if n == "class":
        return True
    if tag == "a":
        return n in ("href", "title", "target", "rel", "style")
    if tag == "img":
        if n == "src":
            return _safe_img_src(value)
        return n in ("alt", "width", "height", "style", "class", "loading")
    if n == "style":
        return True
    return False


def _remove_ql_image_selected_class(html: str) -> str:
    """Убирает класс выделения редактора с <img> (не должен попадать в опубликованный HTML)."""
    if not html or "ql-image-selected" not in html:
        return html

    def clean_img_tag(match: re.Match) -> str:
        tag = match.group(0)

        def strip_from_quoted_class(m: re.Match) -> str:
            q = m.group(1)
            inner = m.group(2)
            parts = [p for p in inner.split() if p and p != "ql-image-selected"]
            if not parts:
                return ""
            return f"class={q}{' '.join(parts)}{q}"

        out = re.sub(
            r"""\bclass\s*=\s*(["'])([^"']*)\1""",
            strip_from_quoted_class,
            tag,
            flags=re.I,
        )
        out = re.sub(r'\sclass\s*=\s*""', "", out, flags=re.I)
        out = re.sub(r"\sclass\s*=\s*''", "", out, flags=re.I)
        out = re.sub(r"\s{2,}", " ", out)
        return out

    return re.sub(r"<img\b[^>]*>", clean_img_tag, html, flags=re.I)


def _strip_rawtext_dangerous_blocks(html: str) -> str:
    """Удаляет целиком script/style: при strip=True bleach убирает только тег, текст внутри остаётся."""
    if not html:
        return ""
    html = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", html)
    html = re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", html)
    html = re.sub(r"(?is)<iframe\b[^>]*>.*?</iframe>", "", html)
    return html


def sanitize_post_html(html: str) -> str:
    if not html:
        return ""
    html = _strip_rawtext_dangerous_blocks(html)
    cleaned = bleach.clean(
        html,
        tags=list(_ALLOWED_TAGS),
        attributes=_attr,
        css_sanitizer=_css_sanitizer,
        strip=True,
    )
    cleaned = _remove_ql_image_selected_class(cleaned)
    return _ensure_img_lazy(cleaned)


def _ensure_img_lazy(html: str) -> str:
    parts: list[str] = []
    last = 0
    for m in re.finditer(r"<img\b[^>]*>", html, re.I):
        chunk = m.group(0)
        if not re.search(r"\bloading\s*=", chunk, re.I):
            chunk = re.sub(r"<img\b", '<img loading="lazy"', chunk, count=1, flags=re.I)
        parts.append(html[last : m.start()])
        parts.append(chunk)
        last = m.end()
    parts.append(html[last:])
    return "".join(parts)


def sanitize_title(text: str, max_length: int = 255) -> str:
    if not text:
        return ""
    t = bleach.clean(text, tags=[], strip=True)
    return t[:max_length]
