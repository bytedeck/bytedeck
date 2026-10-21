"""Take the submission's course stamp out of the model, keeping its column for now (#2875).

Release one of CONTRIBUTING.md's two-release drop ("Migrations and the deploy window"): the
outgoing version still selects the column while this deploys, so it stays in the database
until a later migration drops it with RunSQL.

The column's foreign key goes now, though. Nothing that knows about the column runs once this
ships, so nothing would clear it when a course is deleted, and the constraint would refuse to
delete any course an old submission still names. The outgoing version never relied on the
constraint, so dropping it is safe while it is still serving.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("quest_manager", "0058_link_submissions_to_registrations"),
    ]

    operations = [
        migrations.AlterField(
            model_name="questsubmission",
            name="course",
            field=models.ForeignKey(
                blank=True,
                db_constraint=False,
                help_text="The course this submission's XP counts toward.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="courses.course",
            ),
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # the column stays exactly as it is
            state_operations=[migrations.RemoveField(model_name="questsubmission", name="course")],
        ),
    ]
