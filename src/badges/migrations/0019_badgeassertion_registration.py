import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("badges", "0018_normalize_badge_fa_icon_names"),
        ("courses", "0035_markrange_color_headers"),
    ]

    operations = [
        migrations.AddField(
            model_name="badgeassertion",
            name="registration",
            field=models.ForeignKey(
                blank=True,
                help_text="The course registration this badge's XP counts toward.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="courses.coursestudent",
            ),
        ),
    ]
