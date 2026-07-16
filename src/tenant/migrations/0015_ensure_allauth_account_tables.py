# Self-healing repair for schemas whose django-allauth `account` tables are
# missing even though the migration history records them as applied.
#
# Background: on long-lived databases (production/staging public schema, some
# development environments) the early `account` migrations were recorded as
# applied without the tables ever being created (faked history from when
# allauth was first added). Nothing touched those tables for years, so the
# inconsistency was invisible — until the django-allauth upgrade (>=65, from
# the Django 5.2 dep-modernization) shipped account.0003, whose ALTER against
# account_emailaddress crashes with 'relation "account_emailaddress" does not
# exist' and blocks `migrate_schemas` (and therefore every deploy).
#
# This migration runs BEFORE account.0003 (run_before) and creates any missing
# account tables using the historical model state as of account.0002, so 0003+
# can then apply normally. On healthy schemas — including fresh databases,
# where account.0001/0002 really run first thanks to the dependency below —
# every table already exists and this is a no-op.

from django.db import migrations


def ensure_allauth_account_tables(apps, schema_editor):
    """Create any missing django-allauth `account` tables in the schema
    currently being migrated.

    Uses the historical model state (as of account.0002, per this migration's
    dependencies), so the created tables match what the recorded-but-never-run
    migrations should have produced; later account migrations then apply
    cleanly on top. Table existence is checked through the connection's
    introspection, which respects the active schema's search_path under
    django-tenants, so each schema is repaired (or skipped) independently.
    """
    connection = schema_editor.connection
    existing_tables = set(connection.introspection.table_names())
    # EmailAddress first: EmailConfirmation has a foreign key to it.
    for model_name in ("EmailAddress", "EmailConfirmation"):
        model = apps.get_model("account", model_name)
        if model._meta.db_table not in existing_tables:
            schema_editor.create_model(model)


class Migration(migrations.Migration):

    dependencies = [
        ("tenant", "0014_auto_20231116_0308"),
        # Pin the historical model state the tables are created from.
        ("account", "0002_email_max_length"),
    ]

    # Guarantee this repair runs before the first allauth migration that
    # executes SQL against account_emailaddress on upgraded installs.
    run_before = [
        ("account", "0003_alter_emailaddress_create_unique_verified_email"),
    ]

    operations = [
        # Reverse is a no-op: we never want to drop the tables on rollback.
        migrations.RunPython(ensure_allauth_account_tables, migrations.RunPython.noop),
    ]
