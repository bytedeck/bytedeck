import django.db.models.deletion
from django.db import migrations, models


def clear_pointer_unless_open(apps, schema_editor):
    """Leave the deck with no active semester unless the one it points at is open (issue #1177).

    A deck that had archived its semester kept pointing at it, because that was the only way to
    stop students joining a course. Now that "no semester is open" is a state the deck can sit
    in, those decks get an empty pointer instead, which is what they always meant.
    """
    SiteConfig = apps.get_model('siteconfig', 'SiteConfig')
    SiteConfig.objects.exclude(active_semester__status='open').update(active_semester=None)


def point_at_newest_semester(apps, schema_editor):
    """Reverse: the pointer is about to become NOT NULL again, so every deck needs one.

    The newest semester is the best available guess, matching the fallback the old field
    default used. A deck with no semesters at all gets one, since the column can't be filled
    otherwise.
    """
    SiteConfig = apps.get_model('siteconfig', 'SiteConfig')
    Semester = apps.get_model('courses', 'Semester')
    for config in SiteConfig.objects.filter(active_semester__isnull=True):
        semester = Semester.objects.order_by('-first_day').first()
        if semester is None:
            semester = Semester.objects.create(status='open')
        config.active_semester = semester
        config.save()


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0029_semester_status"),
        ("siteconfig", "0032_remove_siteconfig_enable_submission_questions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="siteconfig",
            name="active_semester",
            field=models.ForeignKey(
                blank=True,
                help_text="The semester students join and earn XP in. It is empty between semesters, when no semester is open.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to="courses.semester",
                verbose_name="Active Semester",
            ),
        ),
        migrations.RunPython(clear_pointer_unless_open, point_at_newest_semester),
    ]
