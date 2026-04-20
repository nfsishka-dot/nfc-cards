"""Оптимизация загруженных изображений (resize + сжатие), без изменения UI."""
from __future__ import annotations

from io import BytesIO

from PIL import Image, ImageOps

# Поддержка HEIC/HEIF (iPhone gallery). Без этого Pillow не читает часть фото.
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except Exception:
    # В dev/CI пакет может быть не установлен; тогда просто работаем без HEIF.
    pass


def optimize_editor_image(
    raw: bytes,
    max_edge: int,
    max_pixels: int,
    jpeg_quality: int = 85,
    webp_quality: int = 82,
) -> tuple[bytes, str]:
    """
    Возвращает (bytes, suffix с точкой).
    Анимированный GIF не изменяем. Остальное — уменьшение и перекодирование.
    """
    bio = BytesIO(raw)
    probe = Image.open(bio)
    fmt = (probe.format or "").upper()

    if fmt == "GIF":
        try:
            probe.seek(1)
            return raw, ".gif"
        except EOFError:
            pass

    im = Image.open(BytesIO(raw))
    im.load()
    fmt = (im.format or "").upper()

    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass

    w, h = im.size
    if w * h > max_pixels:
        scale = (max_pixels / (w * h)) ** 0.5
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)
        w, h = im.size

    edge = max(w, h)
    if edge > max_edge:
        scale = max_edge / edge
        nw = max(1, int(w * scale))
        nh = max(1, int(h * scale))
        im = im.resize((nw, nh), Image.Resampling.LANCZOS)

    out = BytesIO()

    if fmt == "PNG":
        has_alpha = im.mode in ("RGBA", "LA") or (
            im.mode == "P" and "transparency" in im.info
        )
        if has_alpha:
            im.save(out, format="PNG", optimize=True, compress_level=9)
            return out.getvalue(), ".png"

    if im.mode not in ("RGB", "L"):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        im = bg
    elif im.mode == "L":
        im = im.convert("RGB")

    if fmt == "WEBP":
        im.save(out, format="WEBP", quality=webp_quality, method=4)
        return out.getvalue(), ".webp"

    im.save(out, format="JPEG", quality=jpeg_quality, optimize=True)
    return out.getvalue(), ".jpg"
