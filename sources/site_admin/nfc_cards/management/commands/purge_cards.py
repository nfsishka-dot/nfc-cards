"""
Опасная ручная операция: удалить все карточки/группы/preview drafts и (опционально) сбросить sequences.

Почему это НЕ в миграции:
- Миграции должны быть безопасными и идемпотентными.
- Автоматическое удаление данных при deploy недопустимо для production.

Раньше purge выполнялся внутри миграции 0004 (RunPython) — теперь вынесено сюда.
Запускайте только осознанно: python manage.py purge_cards --force [--reset-sequences]
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from nfc_cards.models import Card, LinkGroup, PreviewDraft, Photo, Video

log = logging.getLogger("nfc_cards.audit")


class Command(BaseCommand):
    help = "Удаляет все Card/LinkGroup/PreviewDraft (опасно). По желанию — сбрасывает sequences."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Подтверждение: без этого флага команда не выполняется (необратимо).",
        )
        parser.add_argument(
            "--reset-sequences",
            action="store_true",
            help="Также сбросить автоинкремент id (SQLite/PostgreSQL).",
        )

    def handle(self, *args, **options):
        if not options["force"]:
            raise CommandError("Отказ: передайте --force для подтверждения необратимого удаления.")

        reset_sequences = bool(options.get("reset_sequences"))
        vendor = connection.vendor

        # Важно: фиксируем количества ДО удаления (delete() возвращает общий счётчик, но без разбивки).
        counts_before = {
            "previewdraft": PreviewDraft.objects.count(),
            "photo": Photo.objects.count(),
            "video": Video.objects.count(),
            "card": Card.objects.count(),
            "linkgroup": LinkGroup.objects.count(),
        }

        with transaction.atomic():
            deleted_preview, _ = PreviewDraft.objects.all().delete()
            deleted_cards, _ = Card.objects.all().delete()
            deleted_groups, _ = LinkGroup.objects.all().delete()

            if reset_sequences:
                with connection.cursor() as cursor:
                    if vendor == "sqlite":
                        cursor.execute(
                            "DELETE FROM sqlite_sequence WHERE name IN ('nfc_cards_card', 'nfc_cards_linkgroup')"
                        )
                    elif vendor == "postgresql":
                        cursor.execute(
                            "SELECT setval(pg_get_serial_sequence('nfc_cards_card', 'id'), 1, false)"
                        )
                        cursor.execute(
                            "SELECT setval(pg_get_serial_sequence('nfc_cards_linkgroup', 'id'), 1, false)"
                        )

        msg = (
            f"purge_cards done vendor={vendor} reset_sequences={int(reset_sequences)} "
            f"deleted_preview={deleted_preview} deleted_cards={deleted_cards} deleted_linkgroups={deleted_groups} "
            f"before={counts_before}"
        )
        log.info(msg)
        self.stdout.write(self.style.WARNING(msg))

