import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("questions", "0003_question_import_id_2"),
    ]

    operations = [
        migrations.AlterField(
            model_name="question",
            name="import_id",
            field=models.UUIDField(
                default=uuid.uuid4,
                help_text="Identifies this question within its quest wherever the quest is shared, so re-importing the quest updates this question rather than a different one. Only change this if you want to disconnect it from the shared version.",
            ),
        ),
        migrations.AddConstraint(
            model_name="question",
            constraint=models.UniqueConstraint(
                fields=("quest", "import_id"), name="unique_question_import_ids"
            ),
        ),
    ]
