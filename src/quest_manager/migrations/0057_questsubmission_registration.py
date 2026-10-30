import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0035_markrange_color_headers"),
        ("quest_manager", "0056_drop_not_null_where_fields_allow_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="questsubmission",
            name="registration",
            field=models.ForeignKey(
                blank=True,
                help_text="The course registration this submission's XP counts toward.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="courses.coursestudent",
            ),
        ),
    ]
