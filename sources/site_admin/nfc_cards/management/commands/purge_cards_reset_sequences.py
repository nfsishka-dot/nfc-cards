"""
Одноразовая опасная операция: удалить все карточки/группы/preview drafts и сбросить sequence id.

Раньше это выполнялось внутри миграции 0004 — в production это недопустимо.
Запуск только явно: python manage.py purge_cards_reset_sequences --yes
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from nfc_cards.models import Card, LinkGroup, PreviewDraft


class Command(BaseCommand):
    help = "Удаляет все Card/LinkGroup/PreviewDraft и сбрасывает автоинкремент id (опасно)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Подтверждение: без этого флага команда не выполняется.",
        )

    def handle(self, *args, **options):
        if not options["yes"]:
            raise CommandError("Отказ: передайте --yes для подтверждения необратимого удаления.")

        PreviewDraft.objects.all().delete()
        Card.objects.all().delete()
        LinkGroup.objects.all().delete()

        with connection.cursor() as cursor:
            if connection.vendor == "sqlite":
                cursor.execute(
                    "DELETE FROM sqlite_sequence WHERE name IN ('nfc_cards_card', 'nfc_cards_linkgroup')"
                )
            elif connection.vendor == "postgresql":
                cursor.execute(
                    "SELECT setval(pg_get_serial_sequence('nfc_cards_card', 'id'), 1, false)"
                )
                cursor.execute(
                    "SELECT setval(pg_get_serial_sequence('nfc_cards_linkgroup', 'id'), 1, false)"
                )

        self.stdout.write(self.style.WARNING("Готово: все карточки и группы удалены, sequences сброшены."))
