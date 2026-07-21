from datetime import date, timedelta
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase

from freezegun import freeze_time

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from tenant.management.commands.deck_status_report import Command
from tenant.models import GRACE_PERIOD_DAYS, Tenant


class DeckStatusReportTest(ByteDeckTenantTestCase):
    """Tests for the read-only `deck_status_report` management command (epic #1729 PR 1)."""

    def test_deck_status_report__lists_deck_with_status_and_writes_nothing(self):
        """The report prints one line per non-public deck (with its billing status and
        stored-vs-fresh count delta) plus a summary, and leaves the Tenant row untouched."""
        cached_before = Tenant.objects.get(pk=self.tenant.pk).active_user_count

        out = StringIO()
        call_command('deck_status_report', stdout=out)
        output = out.getvalue()

        self.assertIn(self.tenant.schema_name, output)
        # the test tenant is created with the model defaults, so it is on trial
        self.assertIn('trial', output)
        self.assertIn('No changes were written.', output)
        # read-only: the stored cached count must not have been refreshed by the report
        self.assertEqual(Tenant.objects.get(pk=self.tenant.pk).active_user_count, cached_before)

    def test_deck_status_report__reports_delta_between_cached_and_fresh_counts(self):
        """A stale cached count shows as a positive delta on the deck's report line.

        Asserted on this deck's own line (not the summary total) because other test
        classes' tenants (e.g. the shared library schema) can coexist in a full-suite run.
        """
        # the shared test schema seeds staff users, so a zeroed cache is guaranteed stale
        Tenant.objects.filter(pk=self.tenant.pk).update(active_user_count=0)

        out = StringIO()
        call_command('deck_status_report', stdout=out)

        tenant_line = next(line for line in out.getvalue().splitlines() if line.startswith(self.tenant.schema_name))
        self.assertRegex(tenant_line, r'\+[1-9]\d*$')
        self.assertIn('with a count delta', out.getvalue())

    def test_deck_status_report__zero_delta_when_cache_is_fresh(self):
        """A deck whose cached count already matches the recomputed count reports a zero delta."""
        fresh = self.tenant.get_active_user_count()
        Tenant.objects.filter(pk=self.tenant.pk).update(active_user_count=fresh)

        out = StringIO()
        call_command('deck_status_report', stdout=out)

        tenant_line = next(line for line in out.getvalue().splitlines() if line.startswith(self.tenant.schema_name))
        self.assertRegex(tenant_line, r'\+0$')


@freeze_time(date(2026, 8, 15))
class BillingStatusLabelTest(SimpleTestCase):
    """Tests for the report's one-word billing-status labels, using unsaved Tenants (no database)."""

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
