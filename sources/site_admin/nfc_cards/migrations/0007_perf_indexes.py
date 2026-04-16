# Generated manually: performance indexes for scale

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nfc_cards", "0006_card_view_password_cipher"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="previewdraft",
            index=models.Index(fields=["created_at"], name="nfc_pd_created_at_idx"),
        ),
        migrations.AddIndex(
            model_name="linkgroup",
            index=models.Index(fields=["-created_at"], name="nfc_lg_created_at_desc_idx"),
        ),
    ]

