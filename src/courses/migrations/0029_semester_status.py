from django.db import migrations, models
from django.utils.timezone import localdate


def _active_semester_id(connection):
    """The deck's active semester, read straight from the siteconfig table.

    Deliberately raw SQL rather than apps.get_model('siteconfig', ...): declaring a
    dependency on siteconfig would pull its migrations (and the SiteConfig row their
    field defaults create) ahead of the tables that row's signals write to. The table
    is missing only on a schema so new that it has no semesters to classify either.

    Returns:
        int or None: the active semester's id, or None when it can't be determined.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('siteconfig_siteconfig')")
        if cursor.fetchone()[0] is None:
            return None
        cursor.execute('SELECT active_semester_id FROM siteconfig_siteconfig LIMIT 1')
        row = cursor.fetchone()
    return row[0] if row else None


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

    if not Semester.objects.exists():
        # a schema being created from scratch has nothing to classify, and its
        # siteconfig table may not exist yet at this point in the migration graph
        return

    active_semester_id = _active_semester_id(schema_editor.connection)
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
