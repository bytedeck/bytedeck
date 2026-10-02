# Self-healing repair for decks whose tables still reject NULL in columns that
# their models allow to be empty (issue #2809).
#
# Background: the app's migrations were started afresh in December 2018 (release
# 0.12.1, "First migrations commit"). Decks that were already running then, such
# as Studio Tyee, recorded the new initial migrations as applied without running
# them, so their tables kept the shape of the models they had been built from.
# The Django 2 upgrade just before it (0.12.0) had let several foreign keys be
# empty, QuestSubmission.semester among them, and those decks never received
# that change: their columns reject NULL, while every deck created since accepts
# it. The difference stayed invisible until code wrote NULL to one of them. Work
# from someone registered in no semester is stamped with no semester (issue
# #2441), so on those decks, starting a quest failed with 'null value in column
# "semester_id" ... violates not-null constraint'.
#
# This migration lets every column accept NULL whose field allows it, in the
# schema being migrated. On a deck built by the migrations the two already
# agree, so it changes nothing there.

from django.db import migrations


def drop_not_null_where_fields_allow_null(apps, schema_editor):
    """Let each column in the schema being migrated accept NULL when its field allows it.

    Compares the historical models with the columns of the current schema, which
    under django-tenants is the deck being migrated, so each deck is repaired, or
    left alone, on its own. Dropping NOT NULL only changes the column's definition:
    no rows are read or rewritten, so it is quick even on a large table.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND is_nullable = 'NO'"
        )
        columns_rejecting_null = set(cursor.fetchall())

    for model in apps.get_models():
        # unmanaged and proxy models have no table of their own for a migration to change
        if not model._meta.managed or model._meta.proxy:
            continue
        table = model._meta.db_table
        for field in model._meta.local_concrete_fields:
            if field.null and (table, field.column) in columns_rejecting_null:
                schema_editor.execute(
                    "ALTER TABLE %s ALTER COLUMN %s DROP NOT NULL"
                    % (schema_editor.quote_name(table), schema_editor.quote_name(field.column))
                )


class Migration(migrations.Migration):

    dependencies = [
        ("quest_manager", "0055_alter_category_map_order"),
    ]

    operations = [
        # Reverse is a no-op: the models allow NULL in these columns, so it is never put back.
        migrations.RunPython(drop_not_null_where_fields_allow_null, migrations.RunPython.noop),
    ]
