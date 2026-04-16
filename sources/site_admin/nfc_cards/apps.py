from django.apps import AppConfig


class NfcCardsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nfc_cards"
    verbose_name = "NFC-открытки"

    def ready(self):
        from . import signals  # noqa: F401

