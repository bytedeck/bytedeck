import importlib

from django.apps import apps as django_apps
from django.db import connection

from django_tenants.test.cases import TenantTestCase

# Migration modules start with a digit, so import via importlib.
ensure_allauth_account_tables = importlib.import_module(
    "tenant.migrations.0015_ensure_allauth_account_tables"
).ensure_allauth_account_tables


class EnsureAllauthAccountTablesTest(TenantTestCase):
    """The 0015_ensure_allauth_account_tables data migration repairs schemas
    whose migration history records django-allauth's `account` migrations as
    applied even though the tables were never created (e.g. the production and
    staging public schemas), which made the allauth >=65 upgrade migration
    account.0003 crash with 'relation "account_emailaddress" does not exist'
    and block every deploy."""

    ACCOUNT_TABLES = ("account_emailaddress", "account_emailconfirmation")

    def _existing_account_tables(self):
        """Return the subset of allauth account tables present in the current schema."""
        return {t for t in connection.introspection.table_names() if t in self.ACCOUNT_TABLES}

    def _run_migration_function(self):
        """Invoke the migration's RunPython callable the way the executor would."""
        with connection.schema_editor() as schema_editor:
            ensure_allauth_account_tables(django_apps, schema_editor)

    def test_ensure_allauth_account_tables__recreates_missing_tables(self):
        """When the account tables are missing (phantom migration history), the
        migration recreates them so later allauth migrations can apply."""
        with connection.cursor() as cursor:
            # Confirmation first (it has a FK to emailaddress); CASCADE for safety.
            cursor.execute("DROP TABLE IF EXISTS account_emailconfirmation CASCADE")
            cursor.execute("DROP TABLE IF EXISTS account_emailaddress CASCADE")
        self.assertEqual(self._existing_account_tables(), set())

        self._run_migration_function()

        self.assertEqual(self._existing_account_tables(), set(self.ACCOUNT_TABLES))

    def test_ensure_allauth_account_tables__noop_when_tables_exist(self):
        """On healthy schemas the migration changes nothing and raises nothing."""
        self.assertEqual(self._existing_account_tables(), set(self.ACCOUNT_TABLES))

        self._run_migration_function()  # must not raise (e.g. no duplicate-table error)

        self.assertEqual(self._existing_account_tables(), set(self.ACCOUNT_TABLES))
