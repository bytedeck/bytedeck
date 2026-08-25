import uuid

from django.db import migrations


def give_each_question_its_own_import_id(apps, schema_editor):
    """Stamp every existing question with an import_id of its own.

    0002 added the column with one value shared by every row, which is what Django's
    schema-level default does; the constraint added in 0004 needs them distinct within
    each quest.
    """
    Question = apps.get_model("questions", "Question")
    for question in Question.objects.using(schema_editor.connection.alias).all():
        question.import_id = uuid.uuid4()
        question.save(update_fields=["import_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("questions", "0002_question_import_id_1"),
    ]

    operations = [
        # No reverse: the ids are the questions' identities from here on, and there is
        # nothing to restore them to. Unapplying leaves them in place for 0002 to drop.
        migrations.RunPython(give_each_question_its_own_import_id, migrations.RunPython.noop),
    ]
