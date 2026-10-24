from django.db import migrations, models
import django.db.models.deletion

# Link each competency to the deck's course whose title matches its text course label (titles are
# unique). The label column is still there: the first migration operation only takes it out of
# Django's state.
LINK_COURSES_BY_TITLE = """
    UPDATE competencies_competency AS competency
    SET course_id = course.id
    FROM courses_course AS course
    WHERE competency.course <> '' AND lower(course.title) = lower(competency.course)
"""


class Migration(migrations.Migration):

    dependencies = [
        ('competencies', '0003_competency_course'),
        ('courses', '0035_markrange_color_headers'),
    ]

    operations = [
        # Release one of dropping the text course column (CONTRIBUTING.md, "Migrations and the
        # deploy window"): the outgoing version still reads and writes it during a deploy, so it
        # leaves Django's state here and the column itself is dropped in a later release.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[migrations.RemoveField(model_name='competency', name='course')],
        ),
        migrations.AddField(
            model_name='competency',
            name='course',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='competencies',
                to='courses.course',
                help_text='The course this competency belongs to. Competency pickers show it before the category, e.g. '
                          '"ADST 9: Defining: Choose a design opportunity". Leave it blank for competencies that span '
                          'courses, such as the Core Competencies.',
            ),
        ),
        migrations.RunSQL(LINK_COURSES_BY_TITLE, reverse_sql=migrations.RunSQL.noop),
        migrations.AlterModelOptions(
            name='competency',
            options={'ordering': ['course__title', 'category', 'name'], 'verbose_name_plural': 'competencies'},
        ),
        migrations.AlterModelOptions(
            name='questcompetency',
            options={'ordering': ['competency__course__title', 'competency__category', 'competency__name'],
                     'verbose_name_plural': 'quest competencies'},
        ),
    ]
