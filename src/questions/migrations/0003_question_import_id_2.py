import uuid

from django.db import migrations


def give_each_question_its_own_import_id(apps, schema_editor):
    """Stamp every existing question with an import_id of its own.

    0002 added the column with one value shared by every row, which is what Django's
    schema-level default does; the constraint added in 0004 needs them distinct within
    each quest.

    Written with a queryset update per row rather than a model save, so nothing but the
    new id is touched: a save would put the rest of a historic row through the model's
    own machinery, and this migration has no business rejecting or rewriting a value it
    is not here to change.

    Args:
        apps (StateApps): the historical model registry, which gives back Question as it
            stands at this point in the migration graph.
        schema_editor (BaseDatabaseSchemaEditor): the editor for the schema being
            migrated, read for the database alias so the rows written are that tenant's.

    Returns:
        None: the rows are updated in place.
    """
    Question = apps.get_model("questions", "Question")
    questions = Question.objects.using(schema_editor.connection.alias)
    for pk in questions.values_list("pk", flat=True):
        questions.filter(pk=pk).update(import_id=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ("questions", "0002_question_import_id_1"),
    ]

    operations = [
        # No reverse: the ids are the questions' identities from here on, and there is
        # nothing to restore them to. Unapplying leaves them in place for 0002 to drop.
        migrations.RunPython(give_each_question_its_own_import_id, migrations.RunPython.noop),
    ]
