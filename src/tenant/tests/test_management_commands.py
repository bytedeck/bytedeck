from datetime import date, timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase

from allauth.account.models import EmailAddress
from django_tenants.utils import get_public_schema_name, schema_context
from freezegun import freeze_time
from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from library.utils import get_library_schema_name
from siteconfig.models import SiteConfig
from tenant.management.commands.deck_status_report import Command
from tenant.models import GRACE_PERIOD_DAYS, Tenant

User = get_user_model()


class DeckStatusReportTest(ByteDeckTenantTestCase):
    """Tests for the read-only `deck_status_report` management command (epic #1729 PR 1)."""

    def run_report(self):
        """Run the command and return its full stdout."""
        out = StringIO()
        call_command('deck_status_report', stdout=out)
        return out.getvalue()

    def tenant_line(self, output, schema_name):
        """Return the report line for the given schema, or fail if it's absent."""
        matches = [line for line in output.splitlines() if line.startswith(schema_name)]
        self.assertEqual(len(matches), 1, f"expected exactly one report line for {schema_name}:\n{output}")
        return matches[0]

    def make_schemaless_tenant(self, name):
        """Create a Tenant row without creating its Postgres schema (fast, and lets tests
        exercise rows the command must skip or report as errors)."""
        with schema_context(get_public_schema_name()):
            tenant = Tenant(name=name, schema_name=name)
            tenant.auto_create_schema = False
            tenant.full_clean()
            tenant.save()
        return tenant

    def test_deck_status_report__lists_deck_with_status_and_writes_nothing(self):
        """The report prints the deck's own line with its billing status plus a summary,
        and leaves the Tenant row untouched."""
        cached_before = Tenant.objects.get(pk=self.tenant.pk).active_user_count

        output = self.run_report()

        # the test tenant is created with the model defaults, so it is on trial;
        # assert on its own line so the 'trial_end' column header can't mask a failure
        self.assertIn(' trial ', self.tenant_line(output, self.tenant.schema_name))
        self.assertIn('No changes were written.', output)
        # read-only: the stored cached count must not have been refreshed by the report
        self.assertEqual(Tenant.objects.get(pk=self.tenant.pk).active_user_count, cached_before)

    def test_deck_status_report__reports_delta_between_cached_and_fresh_counts(self):
        """A stale cached count shows as a positive delta on the deck's report line.

        Asserted on this deck's own line (not the summary total) because other test
        classes' tenants can coexist in a full-suite run.
        """
        # register a student so the fresh (students-only) count is non-zero, then
        # zero the cache so it is guaranteed stale
        student = baker.make(User)
        baker.make('courses.CourseStudent', user=student, semester=SiteConfig.get().active_semester)
        Tenant.objects.filter(pk=self.tenant.pk).update(active_user_count=0)

        output = self.run_report()

        self.assertRegex(self.tenant_line(output, self.tenant.schema_name), r'\+[1-9]\d*$')
        self.assertIn('with a count delta', output)

    def test_deck_status_report__zero_delta_when_cache_is_fresh(self):
        """A deck whose cached count already matches the recomputed count reports a zero delta."""
        fresh = self.tenant.get_active_user_count()
        Tenant.objects.filter(pk=self.tenant.pk).update(active_user_count=fresh)

        output = self.run_report()

        self.assertRegex(self.tenant_line(output, self.tenant.schema_name), r'\+0$')

    def test_deck_status_report__excludes_library_schema(self):
        """The shared-library tenant is not a billable deck and must not appear in the report."""
        library_name = get_library_schema_name()
        # a real library tenant may already exist when the full suite runs; only fabricate
        # one (schema-less, fast) when running standalone
        if not Tenant.objects.filter(schema_name=library_name).exists():
            self.make_schemaless_tenant(library_name)

        output = self.run_report()

        self.assertNotIn(library_name, output)
        self.assertIn(self.tenant.schema_name, output)

    def test_deck_status_report__broken_schema_reported_as_error_line(self):
        """A deck whose schema is missing/broken gets an ERROR line and the report continues
        to the remaining decks instead of aborting."""
        self.make_schemaless_tenant('brokendeck')

        output = self.run_report()

        self.assertIn(' ERROR ', self.tenant_line(output, 'brokendeck'))
        self.assertIn('1 with errors', output)
        # the healthy deck is still fully reported after the broken one
        self.assertIn(' trial ', self.tenant_line(output, self.tenant.schema_name))


@freeze_time("2026-08-15 20:00:00")
class BillingStatusLabelTest(SimpleTestCase):
    """Tests for the report's one-word billing-status labels, using unsaved Tenants (no database).

    The clock is frozen at midday UTC so timezone.localdate() (America/Vancouver) falls
    on the same calendar date.
    """

    def test_billing_status__labels_for_each_state(self):
        """Each derived billing state maps to its one-word report label."""
        today = date(2026, 8, 15)
        self.assertEqual(Command.billing_status(Tenant(paid_until=today)), 'subscribed')
        self.assertEqual(Command.billing_status(Tenant(paid_until=today - timedelta(days=5), trial_end_date=None)), 'grace')
        self.assertEqual(Command.billing_status(Tenant(trial_end_date=today, paid_until=None)), 'trial')
        self.assertEqual(
            Command.billing_status(
                Tenant(trial_end_date=today - timedelta(days=1), paid_until=today - timedelta(days=GRACE_PERIOD_DAYS + 1))
            ),
            'suspended',
        )
        self.assertEqual(Command.billing_status(Tenant(trial_end_date=None, paid_until=None)), 'unmanaged')


class BackfillOwnerEmailsTest(ByteDeckTenantTestCase):
    """Tests for the `backfill_owner_emails` management command (#1729 rollout)."""

    def run_command(self, *args):
        """Run the command and return its full stdout."""
        out = StringIO()
        call_command('backfill_owner_emails', *args, stdout=out)
        return out.getvalue()

    def deck_line(self, output):
        """Return this test deck's audit line, or fail if it's absent."""
        matches = [line for line in output.splitlines() if line.startswith(self.tenant.schema_name)]
        self.assertEqual(len(matches), 1, f"expected exactly one audit line for {self.tenant.schema_name}:\n{output}")
        return matches[0]

    def set_owner(self, **user_fields):
        """Make a fresh staff user the deck owner and return it."""
        owner = baker.make(User, is_staff=True, **user_fields)
        config = SiteConfig.get()
        config.deck_owner = owner
        config.save()
        return owner

    def test_backfill__dry_run_reports_and_writes_nothing(self):
        """Without --apply the command reports the fix it would make, but writes no
        EmailAddress row and leaves the cached owner email untouched."""
        owner = self.set_owner(email='legacy.owner@example.com')
        output = self.run_command()
        self.assertIn('would-fix', self.deck_line(output))
        self.assertIn('Dry run: no changes were written', output)
        self.assertFalse(EmailAddress.objects.filter(user=owner).exists())

    def test_backfill__apply_normalizes_bookkeeping_and_refreshes_cache(self):
        """--apply creates the owner's EmailAddress verified+primary, demotes any
        other primary address, lands owner_email_cached immediately, and a second
        run reports the deck as already ok (idempotent)."""
        owner = self.set_owner(email='legacy.owner@example.com')
        stale_primary = EmailAddress.objects.create(user=owner, email='old.address@example.com', verified=False, primary=True)

        output = self.run_command('--apply')
        self.assertIn(' fixed', self.deck_line(output))
        address = EmailAddress.objects.get(user=owner, email='legacy.owner@example.com')
        self.assertTrue(address.verified)
        self.assertTrue(address.primary)
        stale_primary.refresh_from_db()
        self.assertFalse(stale_primary.primary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.owner_email_cached, 'legacy.owner@example.com')

        self.assertIn(' ok', self.deck_line(self.run_command()))

    def test_backfill__flags_owners_needing_a_human(self):
        """An owner with no email is reported with nothing written, the deprecated
        public-tenant owner_email is surfaced as a clue, and a deck still on the
        heuristic default owner account is flagged."""
        from django.conf import settings

        # move the seeded default-owner username out of the way so the fresh owner
        # can carry it (usernames are unique per schema)
        User.objects.filter(username=settings.TENANT_DEFAULT_OWNER_USERNAME).update(username='renamed-for-test')
        owner = self.set_owner(email='')
        User.objects.filter(pk=owner.pk).update(username=settings.TENANT_DEFAULT_OWNER_USERNAME)
        Tenant.objects.filter(pk=self.tenant.pk).update(owner_email='clue@example.com')

        output = self.run_command('--apply')
        line = self.deck_line(output)
        self.assertIn('no-email', line)
        self.assertIn('default owner account', line)
        self.assertIn('clue@example.com', line)
        self.assertFalse(EmailAddress.objects.filter(user=owner).exists())
        self.assertIn('1 with no owner email', output)

    def test_backfill__existing_unverified_row_is_marked_not_duplicated(self):
        """--apply promotes an existing unverified, non-primary EmailAddress row for
        the owner's address in place: no duplicate row is created."""
        owner = self.set_owner(email='legacy.owner@example.com')
        EmailAddress.objects.create(user=owner, email='legacy.owner@example.com', verified=False, primary=False)

        output = self.run_command('--apply')
        self.assertIn(' fixed', self.deck_line(output))
        rows = EmailAddress.objects.filter(user=owner)
        self.assertEqual(rows.count(), 1)
        self.assertTrue(rows[0].verified)
        self.assertTrue(rows[0].primary)

    def test_backfill__broken_schema_reported_as_error_line(self):
        """A Tenant row whose schema doesn't exist is reported as an ERROR line (and
        counted in the summary) without aborting the run for the remaining decks."""
        with schema_context(get_public_schema_name()):
            broken = Tenant(name='brokendeck', schema_name='brokendeck')
            broken.auto_create_schema = False
            broken.full_clean()
            broken.save()

        output = self.run_command()
        broken_line = [line for line in output.splitlines() if line.startswith('brokendeck')]
        self.assertEqual(len(broken_line), 1)
        self.assertIn('ERROR', broken_line[0])
        self.assertIn('1 with errors', output)
        # the healthy test deck was still processed after the broken one
        self.deck_line(output)
