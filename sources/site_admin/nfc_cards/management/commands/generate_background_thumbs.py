"""Генерация WebP-превью в …/thumbs/ рядом с полноразмерными фонами."""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image

_THUMB_MAX = (300, 500)
_WEBP_QUALITY = 82
_ALLOWED = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


class Command(BaseCommand):
    help = "Создать thumbnails (WebP) в static/hexgraph/backgrounds/**/thumbs/"

    def handle(self, *args, **options):
        bg_dir = Path(settings.BASE_DIR) / "static" / "hexgraph" / "backgrounds"
        if not bg_dir.is_dir():
            self.stdout.write(self.style.WARNING("backgrounds dir missing"))
            return

        n = 0
        for full_path in sorted(bg_dir.rglob("*")):
            if not full_path.is_file():
                continue
            if full_path.suffix.lower() not in _ALLOWED:
                continue
            try:
                rel = full_path.relative_to(bg_dir)
            except ValueError:
                continue
            if "thumbs" in rel.parts:
                continue
            if rel.name.startswith("."):
                continue

            thumbs_dir = full_path.parent / "thumbs"
            thumbs_dir.mkdir(parents=True, exist_ok=True)
            out_path = thumbs_dir / f"{full_path.stem}.webp"
            if out_path.exists():
                continue

            try:
                im = Image.open(full_path)
                im = im.convert("RGBA") if im.mode in ("P", "RGBA") else im.convert("RGB")
                im.thumbnail(_THUMB_MAX, Image.Resampling.LANCZOS)
                im.save(out_path, "WEBP", quality=_WEBP_QUALITY, method=6)
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"skip {rel}: {e}"))
                continue
            n += 1
            self.stdout.write(f"OK {out_path.relative_to(bg_dir)}")

        self.stdout.write(self.style.SUCCESS(f"created {n} thumbnails"))
