import importlib

from django.apps import apps as django_apps
from django.db import connection

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

# Migration modules start with a digit, so import via importlib.
ensure_allauth_account_tables = importlib.import_module(
    "tenant.migrations.0015_ensure_allauth_account_tables"
).ensure_allauth_account_tables
repoint_links = importlib.import_module(
    "tenant.migrations.0031_repoint_homepage_deck_request_links"
).repoint_links


class EnsureAllauthAccountTablesTest(ByteDeckTenantTestCase):
    # Drops and recreates account tables in its own schema; use a private,
    # fresh schema rather than the shared reused one so the destructive DDL
    # can't affect other classes (and doesn't collide with the shared tenant).
    reuse_schema = False

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


class RepointHomepageDeckRequestLinksTest(ByteDeckTenantTestCase):
    """The 0031 data migration repoints hardcoded deck-request links in flatpage content.

    The homepage is a FlatPage that `initdb` creates with `get_or_create`, so a site set up
    before the deck-request flow moved keeps the content it was seeded with however many
    times initdb is re-run. The seeded HTML being correct says nothing about what any
    existing deck actually stores, and a TRY IT button left on /decks/request/new/ answers
    an ordinary visitor with a 403 rather than a form (issue #2716).
    """

    def run_migration(self):
        """Invoke the migration's RunPython callable the way the executor would."""
        with connection.schema_editor() as schema_editor:
            repoint_links(django_apps, schema_editor)

    def flatpage(self, content):
        """Create a flatpage holding `content` and return it.

        Args:
            content: the stored HTML to start from.

        Returns:
            FlatPage: the saved page, ready to re-read after the migration runs.
        """
        from django.contrib.flatpages.models import FlatPage

        return FlatPage.objects.create(url="/home/", title="Home", content=content)

    def test_repoint_links__sends_the_gated_form_link_to_the_request_form(self):
        """/decks/request/new/ is the step *after* email verification, so it 403s a visitor
        who has not been through the flow. A homepage button has to start them at the top."""
        page = self.flatpage('<a href="/decks/request/new/" role="button">TRY IT</a>')

        self.run_migration()

        page.refresh_from_db()
        self.assertIn('href="/decks/request/"', page.content)
        self.assertNotIn("/decks/request/new/", page.content)

    def test_repoint_links__repoints_the_urls_that_no_longer_exist(self):
        """The two paths the flow used before it moved, which now 404."""
        page = self.flatpage(
            '<a href="/decks/new/">TRY IT</a>'
            "<a href='/decks/request-new-deck/'>TRY IT!</a>"
        )

        self.run_migration()

        page.refresh_from_db()
        self.assertEqual(page.content.count("/decks/request/"), 2)
        self.assertNotIn("/decks/new/", page.content)
        self.assertNotIn("/decks/request-new-deck/", page.content)

    def test_repoint_links__leaves_the_rest_of_the_page_alone(self):
        """Only those exact href values change, so a homepage someone has edited keeps every
        other change they made, including a link that is already right."""
        original = (
            '<h1>ByteDeck</h1><a href="/decks/request/">TRY IT</a>'
            '<a href="/accounts/login/">Sign in</a><p>Read about /decks/new/ in our docs.</p>'
        )
        page = self.flatpage(original)

        self.run_migration()

        page.refresh_from_db()
        self.assertEqual(page.content, original)
