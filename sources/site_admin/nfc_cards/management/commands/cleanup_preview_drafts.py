from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from nfc_cards.models import PreviewDraft


class Command(BaseCommand):
    help = "Удаляет старые черновики preview (освобождение БД)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=None,
            help="Удалить черновики старше N часов (по умолчанию из PREVIEW_DRAFT_MAX_AGE_HOURS или 2).",
        )

    def handle(self, *args, **options):
        from django.conf import settings

        hours = options["hours"]
        if hours is None:
            hours = int(getattr(settings, "PREVIEW_DRAFT_MAX_AGE_HOURS", 2))
        cutoff = timezone.now() - timedelta(hours=hours)
        deleted, _ = PreviewDraft.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(
            self.style.SUCCESS(f"Удалено черновиков preview (старше {hours} ч.): {deleted}")
        )
