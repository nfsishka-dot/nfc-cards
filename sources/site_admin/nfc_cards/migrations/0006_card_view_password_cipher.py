# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("nfc_cards", "0005_card_view_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="view_password_cipher",
            field=models.TextField(blank=True, default=""),
        ),
    ]
