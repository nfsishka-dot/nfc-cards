from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("nfc_cards", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="background",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
