"""Нормализация и URL фона открытки (Quill / preview / post)."""
from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings

# Допустимые id паттернов (hexgraph/patterns/<id>.svg)
BACKGROUND_PATTERN_IDS = frozenset(
    {
        "bg-hearts-soft",
        "bg-hearts-drift",
        "bg-hearts-bloom",
        "bg-confetti-light",
        "bg-celebration-glow",
        "bg-party-dust",
        "bg-gift-minimal",
        "bg-gift-wrap",
        "bg-magic-twinkle",
        "bg-magic-trail",
        "bg-soft-petal",
        "bg-soft-haze",
        "bg-fun-rise",
        "bg-message-airmail",
        "bg-minimal-grain",
    }
)

_BG_PUBLIC_PREFIX = "hexgraph/backgrounds/"
_ALLOWED_RASTER_EXT = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"})


def normalize_hex_color(v):
    if not isinstance(v, str) or not v.startswith("#"):
        return None
    h = v[1:].strip()
    if len(h) == 3 and all(c in "0123456789abcdefABCDEF" for c in h):
        h = "".join(c * 2 for c in h)
    if len(h) == 6 and all(c in "0123456789abcdefABCDEF" for c in h):
        return "#" + h.lower()
    return None


def normalize_background(bg):
    """Приводит JSON фона к безопасному виду; неизвестный pattern → цвет."""
    if not isinstance(bg, dict) or not bg.get("type"):
        return {"type": "color", "value": "#ffffff"}
    t = bg.get("type")
    if t == "color":
        nv = normalize_hex_color(bg.get("value"))
        if nv:
            return {"type": "color", "value": nv}
        return {"type": "color", "value": "#ffffff"}
    if t == "image":
        v = bg.get("value")
        if isinstance(v, str) and v and ".." not in v and not v.startswith("/"):
            return {"type": "image", "value": v}
        return {"type": "color", "value": "#ffffff"}
    if t == "pattern":
        v = bg.get("value")
        if isinstance(v, str) and v in BACKGROUND_PATTERN_IDS:
            return {"type": "pattern", "value": v}
        return {"type": "color", "value": "#ffffff"}
    return {"type": "color", "value": "#ffffff"}


def background_media_url(background):
    """URL картинки или тайлового SVG для body/preview."""
    if not isinstance(background, dict):
        return ""
    t = background.get("type")
    v = background.get("value") or ""
    if t == "image" and v:
        return settings.STATIC_URL + v.lstrip("/")
    if t == "pattern" and v in BACKGROUND_PATTERN_IDS:
        return settings.STATIC_URL + f"hexgraph/patterns/{v}.svg"
    return ""


def parse_background(raw):
    if not raw:
        return {"type": "color", "value": "#ffffff"}
    try:
        bg = json.loads(raw)
    except Exception:
        return {"type": "color", "value": "#ffffff"}
    if not isinstance(bg, dict) or not bg.get("type"):
        return {"type": "color", "value": "#ffffff"}
    return normalize_background(bg)


def _bg_dir() -> Path:
    return Path(settings.BASE_DIR) / "static" / "hexgraph" / "backgrounds"


def _to_public(rel: Path) -> str:
    rel_posix = rel.as_posix().lstrip("./")
    return _BG_PUBLIC_PREFIX + rel_posix


def _thumb_candidates(full_path: Path) -> list[Path]:
    stem = full_path.stem
    thumbs_dir = full_path.parent / "thumbs"
    for ext in (".webp", ".jpg", ".jpeg", ".png"):
        yield thumbs_dir / f"{stem}{ext}"


def list_background_images() -> list[dict[str, str]]:
    """
    Список фонов для редактора: { "full": "hexgraph/backgrounds/...", "thumb": "..." }.
    Файлы в каталогах thumbs не считаются full. Если превью нет — thumb == full (обратная совместимость).
    """
    bg_dir = _bg_dir()
    if not bg_dir.is_dir():
        return []

    out: list[dict[str, str]] = []
    for full_path in sorted(bg_dir.rglob("*")):
        if not full_path.is_file():
            continue
        if full_path.suffix.lower() not in _ALLOWED_RASTER_EXT:
            continue
        try:
            rel = full_path.relative_to(bg_dir)
        except ValueError:
            continue
        if "thumbs" in rel.parts:
            continue
        if rel.name.startswith("."):
            continue

        full_pub = _to_public(rel)
        thumb_pub = full_pub
        for cand in _thumb_candidates(full_path):
            if cand.is_file():
                thumb_rel = cand.relative_to(bg_dir)
                thumb_pub = _to_public(thumb_rel)
                break
        out.append({"full": full_pub, "thumb": thumb_pub})

    out.sort(key=lambda x: x["full"].lower())
    return out
