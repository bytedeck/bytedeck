import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    # Adding a unique, non-nullable field over the next three migrations, per
    # https://docs.djangoproject.com/en/5.2/howto/writing-migrations/#migrations-that-add-unique-fields
    # (the same three-step badges/0006-0008 used for Badge.import_id). A single AddField
    # would give every existing row the one value the default was called for.

    dependencies = [
        ("questions", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="question",
            name="import_id",
            field=models.UUIDField(
                default=uuid.uuid4,
                null=True,
                help_text="Identifies this question within its quest wherever the quest is shared, so re-importing the quest updates this question rather than a different one. Only change this if you want to disconnect it from the shared version.",
            ),
        ),
    ]
