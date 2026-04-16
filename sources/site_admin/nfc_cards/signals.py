from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Card
from .services.card_post_cache import invalidate_published_post_cache

_POST_RENDER_FIELDS = frozenset(
    {
        "title",
        "content",
        "background",
        "background_color",
        "view_password_hash",
        "view_password_cipher",
        "published_at",
        "is_published",
    }
)


@receiver(post_save, sender=Card)
def invalidate_card_post_cache_on_change(sender, instance, update_fields=None, **kwargs):
    if update_fields is not None and not _POST_RENDER_FIELDS.intersection(update_fields):
        return
    invalidate_published_post_cache(instance)
