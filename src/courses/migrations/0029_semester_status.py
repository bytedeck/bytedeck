from django.db import migrations, models
from django.utils.timezone import localdate


def set_status_from_closed(apps, schema_editor):
    """Give every existing semester a lifecycle status (issue #2157).

    The old model had one boolean (closed) plus a SiteConfig pointer at the active
    semester, so the three lifecycle stages have to be reconstructed:

    * closed -> ARCHIVED: final marks were recorded, which is exactly ARCHIVED.
    * the deck's active semester -> OPEN: students are registered in it right now.
    * everything else is inert today (neither closed nor pointed at). Those are split
      by date rather than all being archived, so a semester a teacher created in
      advance for next term stays usable: still to come -> UPCOMING, already over
      (or undated) -> ARCHIVED. Registrations are deliberately left untouched, since
      these semesters never had final marks recorded.
    """
    Semester = apps.get_model('courses', 'Semester')
    SiteConfig = apps.get_model('siteconfig', 'SiteConfig')

    siteconfig = SiteConfig.objects.first()  # None on schemas without one (e.g. public)
    active_semester_id = siteconfig.active_semester_id if siteconfig else None
    today = localdate()

    for semester in Semester.objects.all():
        if semester.closed:
            status = 'archived'
        elif semester.pk == active_semester_id:
            status = 'open'
        elif semester.last_day is not None and semester.last_day >= today:
            status = 'upcoming'
        else:
            status = 'archived'

        semester.status = status
        semester.save(update_fields=['status'])


def set_closed_from_status(apps, schema_editor):
    """Restore the closed boolean from status, so this migration can be reversed."""
    Semester = apps.get_model('courses', 'Semester')
    Semester.objects.filter(status='archived').update(closed=True)
    Semester.objects.exclude(status='archived').update(closed=False)


class Migration(migrations.Migration):

    dependencies = [
        ('siteconfig', '0032_remove_siteconfig_enable_submission_questions'),
        ('courses', '0028_semester_name'),
    ]

    operations = [
        migrations.AddField(
            model_name='semester',
            name='status',
            field=models.CharField(
                choices=[('upcoming', 'Upcoming'), ('open', 'Open'), ('archived', 'Archived')],
                default='upcoming',
                help_text='Upcoming: still being set up. Open: students can be registered in it and earn XP. '
                          'Archived: final marks have been recorded and it can no longer be changed.',
                max_length=10,
            ),
        ),
        migrations.RunPython(set_status_from_closed, set_closed_from_status),
        migrations.RemoveField(
            model_name='semester',
            name='closed',
        ),
    ]
