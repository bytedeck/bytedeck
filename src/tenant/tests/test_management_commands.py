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
        # a lapsed trial in its unified grace window also reads as grace (#1734 B4)
        self.assertEqual(Command.billing_status(Tenant(trial_end_date=today - timedelta(days=5), paid_until=None)), 'grace')
        self.assertEqual(
            Command.billing_status(
                Tenant(
                    trial_end_date=today - timedelta(days=GRACE_PERIOD_DAYS + 40),
                    paid_until=today - timedelta(days=GRACE_PERIOD_DAYS + 1),
                )
            ),
            'suspended',
        )
        self.assertEqual(Command.billing_status(Tenant(trial_end_date=None, paid_until=None)), 'unmanaged')


class StripeBackfillReportTest(ByteDeckTenantTestCase):
    """Tests for the read-only #2043 legacy backfill report (plan §10.3)."""

    def call(self):
        """Run the command and return its stdout."""
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command('stripe_backfill_report', stdout=out)
        return out.getvalue()

    def test_report__not_configured(self):
        """Without a secret key the command explains and exits without calling Stripe."""
        output = self.call()
        self.assertIn('not configured', output)

    def test_report__matches_ambiguous_unmatched_and_skips_linked(self):
        """Subscriptions are bucketed by owner-email match; already-linked ones are
        skipped; nothing is ever written."""
        from unittest.mock import MagicMock, patch

        from django.test import override_settings

        from tenant.models import Tenant

        def sub(sub_id, email, customer_id='cus_x'):
            return {'id': sub_id, 'customer': {'id': customer_id, 'email': email}}

        listing = MagicMock()
        # two extra schema-less decks sharing an owner email make an ambiguous bucket
        # (tenant rows can only be created from the public schema)
        from django_tenants.utils import get_public_schema_name, schema_context
        with schema_context(get_public_schema_name()):
            for name in ('twin', 'twin2'):
                twin = Tenant(schema_name=name, name=name, owner_email_cached='shared@example.com')
                twin.auto_create_schema = False
                twin.save()
        Tenant.objects.filter(pk=self.tenant.pk).update(owner_email_cached='owner@example.com')

        listing.auto_paging_iter.return_value = [
            sub('sub_match', 'owner@example.com'),          # exactly one deck
            sub('sub_shared', 'shared@example.com'),        # two decks -> ambiguous
            sub('sub_none', 'stranger@example.com'),        # no deck
            sub('sub_noemail', None),                       # customer without email
        ]
        with override_settings(STRIPE_SECRET_KEY='sk_test_123'):
            with patch('stripe.Subscription.list', return_value=listing):
                output = self.call()

        self.assertIn("sub_match", output)
        self.assertIn(f"deck '{self.tenant.schema_name}'", output)
        self.assertIn('MULTIPLE decks', output)
        self.assertIn('sub_none', output)
        self.assertIn('no deck with this owner email', output)
        self.assertIn('sub_noemail', output)
        self.assertIn('nothing was changed', output)
        # read-only: the matched deck was NOT linked
        self.assertEqual(Tenant.objects.get(pk=self.tenant.pk).stripe_subscription_id, '')

    def test_report__handles_the_sdks_real_subscription_objects(self):
        """The listing yields the SDK's Subscription objects, which are NOT dicts
        on stripe-python 15.x (.get() raises): the report's dict-style reads only
        worked in tests because the doubles were plain dicts (the same drift that
        500ed staging's webhook, 2026-08-09). Pins the seam with the real type."""
        from unittest.mock import MagicMock, patch

        import stripe as stripe_lib

        from django.test import override_settings

        from tenant.models import Tenant

        Tenant.objects.filter(pk=self.tenant.pk).update(owner_email_cached='owner@example.com')
        sdk_sub = stripe_lib.Subscription.construct_from(
            {'id': 'sub_sdk', 'customer': {'id': 'cus_sdk', 'email': 'OWNER@example.com'}}, 'sk_test_x')
        self.assertFalse(hasattr(sdk_sub, 'get'))  # the very property that broke staging

        listing = MagicMock()
        listing.auto_paging_iter.return_value = [sdk_sub]
        with override_settings(STRIPE_SECRET_KEY='sk_test_123'):
            with patch('stripe.Subscription.list', return_value=listing):
                output = self.call()

        self.assertIn('sub_sdk', output)
        self.assertIn(f"deck '{self.tenant.schema_name}'", output)

    def test_report__skips_already_linked_subscriptions(self):
        """A subscription some deck already carries doesn't reappear in the report."""
        from unittest.mock import MagicMock, patch

        from django.test import override_settings

        from tenant.models import Tenant

        Tenant.objects.filter(pk=self.tenant.pk).update(stripe_subscription_id='sub_done')
        listing = MagicMock()
        listing.auto_paging_iter.return_value = [
            {'id': 'sub_done', 'customer': {'id': 'cus_x', 'email': 'x@example.com'}},
        ]
        with override_settings(STRIPE_SECRET_KEY='sk_test_123'):
            with patch('stripe.Subscription.list', return_value=listing):
                output = self.call()
        self.assertNotIn('sub_done', output)


class BackfillOwnerEmailsTest(ByteDeckTenantTestCase):
    """Tests for the `backfill_owner_emails` management command (#1729 rollout)."""

    def run_command(self, *args):
        """Run backfill_owner_emails and capture its report.

        Args:
            *args: Extra command arguments (e.g. '--apply'); none means dry run.

        Returns:
            str: The command's full stdout.
        """
        out = StringIO()
        call_command('backfill_owner_emails', *args, stdout=out)
        return out.getvalue()

    def deck_line(self, output):
        """Extract this test deck's audit line from a command report.

        Args:
            output (str): The command's full stdout.

        Returns:
            str: The single report line for this test's deck (fails the test if
            the line is absent or duplicated).
        """
        matches = [line for line in output.splitlines() if line.startswith(self.tenant.schema_name)]
        self.assertEqual(len(matches), 1, f"expected exactly one audit line for {self.tenant.schema_name}:\n{output}")
        return matches[0]

    def set_owner(self, **user_fields):
        """Make a fresh staff user the deck owner.

        Args:
            **user_fields: Field overrides forwarded to the User baker (e.g. email).

        Returns:
            User: The newly created owner now set as SiteConfig.deck_owner.
        """
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
        """An owner with no email is reported with nothing written, and a deck
        still on the heuristic default owner account is flagged."""
        from django.conf import settings

        # move the seeded default-owner username out of the way so the fresh owner
        # can carry it (usernames are unique per schema)
        User.objects.filter(username=settings.TENANT_DEFAULT_OWNER_USERNAME).update(username='renamed-for-test')
        owner = self.set_owner(email='')
        User.objects.filter(pk=owner.pk).update(username=settings.TENANT_DEFAULT_OWNER_USERNAME)

        output = self.run_command('--apply')
        line = self.deck_line(output)
        self.assertIn('no-email', line)
        self.assertIn('default owner account', line)
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

    def test_backfill__mixed_case_owner_email_normalizes_the_lowercase_row(self):
        """When the owner's User.email is mixed case and both the lowercase row and an
        exact-case duplicate exist, --apply targets the lowercase row (the form
        EmailAddress.clean() stores) and demotes the duplicate's primary, instead of
        lowercasing the duplicate into a unique (user, email) collision with its
        sibling. The cache lands allauth's canonical lowercase form."""
        owner = self.set_owner(email='Mixed.Case@Example.com')
        variant = EmailAddress.objects.create(user=owner, email='Mixed.Case@Example.com', verified=False, primary=True)
        canonical = EmailAddress.objects.create(user=owner, email='mixed.case@example.com', verified=False, primary=False)

        output = self.run_command('--apply')
        self.assertIn(' fixed', self.deck_line(output))
        canonical.refresh_from_db()
        variant.refresh_from_db()
        self.assertTrue(canonical.verified)
        self.assertTrue(canonical.primary)
        self.assertFalse(variant.primary)
        self.assertEqual(EmailAddress.objects.filter(user=owner, primary=True).count(), 1)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.owner_email_cached, 'mixed.case@example.com')

    def test_backfill__mixed_case_owner_email_creates_lowercase_row_idempotently(self):
        """With no existing rows and a mixed-case User.email, --apply stores the new row
        lowercase (EmailAddress.clean() lowercases on save), the cache lands allauth's
        canonical lowercase form, and a second run still reports the deck as ok."""
        owner = self.set_owner(email='Mixed.Case@Example.com')

        self.assertIn(' fixed', self.deck_line(self.run_command('--apply')))
        row = EmailAddress.objects.get(user=owner)
        self.assertEqual(row.email, 'mixed.case@example.com')
        self.assertTrue(row.verified)
        self.assertTrue(row.primary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.owner_email_cached, 'mixed.case@example.com')

        self.assertIn(' ok', self.deck_line(self.run_command()))

    def test_backfill__skips_when_another_account_verified_the_address(self):
        """When a different account on the deck already holds the owner's address
        verified (the DB allows one verified row per address), both dry run and
        --apply report the deck as skipped for a human and write nothing: the
        command must not guess which account is really the owner's."""
        owner = self.set_owner(email='Shared@Example.com')
        other_row = EmailAddress.objects.create(user=baker.make(User), email='shared@example.com', verified=True, primary=True)

        dry_line = self.deck_line(self.run_command())
        self.assertIn('skipped', dry_line)
        self.assertIn('verified by another account', dry_line)

        output = self.run_command('--apply')
        self.assertIn('skipped', self.deck_line(output))
        self.assertIn('1 skipped', output)
        self.assertFalse(EmailAddress.objects.filter(user=owner).exists())
        other_row.refresh_from_db()
        self.assertTrue(other_row.verified)
        self.assertTrue(other_row.primary)

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

    def test_backfill__schema_option_narrows_the_run_to_one_deck(self):
        """--schema processes only the named deck (maintainer request, 2026-08-09:
        clean up a single legacy deck by hand): another tenant row is not touched
        or reported, and the summary counts one deck."""
        with schema_context(get_public_schema_name()):
            other = Tenant(name='otherdeck', schema_name='otherdeck')
            other.auto_create_schema = False
            other.full_clean()
            other.save()
        self.set_owner(email='legacy.owner@example.com')

        output = self.run_command('--schema', self.tenant.schema_name, '--apply')
        self.deck_line(output)  # exactly one line for the named deck
        self.assertNotIn('otherdeck', output)  # the schema-less row would have been an ERROR line
        self.assertIn('1 deck(s)', output)

    def test_backfill__schema_option_rejects_unknown_and_non_deck_schemas(self):
        """--schema with an unknown schema name, or the public schema (not a deck),
        fails loudly instead of silently processing nothing."""
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self.run_command('--schema', 'no_such_deck')
        with self.assertRaises(CommandError):
            self.run_command('--schema', get_public_schema_name())

    def test_backfill__case_variant_primary_demoted_in_favor_of_exact_match(self):
        """When a case-variant duplicate of the owner's address holds primary, --apply
        demotes it (by pk, before the promote saves: the DB's unique_primary_email
        constraint allows only one primary per user) and promotes the exact-case
        row, leaving exactly one verified primary."""
        owner = self.set_owner(email='legacy.owner@example.com')
        exact = EmailAddress.objects.create(user=owner, email='legacy.owner@example.com', verified=False, primary=False)
        variant = EmailAddress.objects.create(user=owner, email='Legacy.Owner@example.com', verified=False, primary=True)

        output = self.run_command('--apply')
        self.assertIn(' fixed', self.deck_line(output))
        exact.refresh_from_db()
        variant.refresh_from_db()
        self.assertTrue(exact.primary)
        self.assertTrue(exact.verified)
        self.assertFalse(variant.primary)
        self.assertEqual(EmailAddress.objects.filter(user=owner, primary=True).count(), 1)


class ChangeDeckOwnerTest(ByteDeckTenantTestCase):
    """Tests for the `change_deck_owner` management command (maintainer request,
    2026-08-09: legacy decks whose owner is the wrong account)."""

    def run_command(self, *args):
        """Run change_deck_owner and capture its output.

        Args:
            *args: The command's positional arguments (schema_name, username).

        Returns:
            str: The command's full stdout.
        """
        out = StringIO()
        call_command('change_deck_owner', *args, stdout=out)
        return out.getvalue()

    def test_change__switches_owner_promotes_superuser_and_refreshes_caches(self):
        """The named staff user becomes SiteConfig.deck_owner, is promoted to
        superuser (mirroring the SiteConfig admin), the deck's cached owner
        fields land immediately, and the output names the handover plus the
        backfill_owner_emails reminder. The previous owner keeps their account."""
        old_owner = SiteConfig.get().deck_owner
        new_owner = baker.make(User, is_staff=True, is_superuser=False,
                               username='newowner', email='new.owner@example.com', first_name='New', last_name='Owner')

        output = self.run_command(self.tenant.schema_name, 'newowner')

        self.assertEqual(SiteConfig.objects.get().deck_owner, new_owner)
        new_owner.refresh_from_db()
        self.assertTrue(new_owner.is_superuser)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.owner_email_cached, 'new.owner@example.com')
        self.assertIn(f'{old_owner.username} -> newowner', output)
        self.assertIn('backfill_owner_emails --schema', output)

    def test_change__already_superuser_new_owner_is_left_as_is(self):
        """A new owner who is already a superuser is simply set as owner."""
        new_owner = baker.make(User, is_staff=True, is_superuser=True, username='superstaff')
        self.run_command(self.tenant.schema_name, 'superstaff')
        self.assertEqual(SiteConfig.objects.get().deck_owner, new_owner)

    def test_change__same_owner_is_a_noop(self):
        """Naming the current owner reports nothing-to-do and changes nothing."""
        owner = SiteConfig.get().deck_owner
        output = self.run_command(self.tenant.schema_name, owner.username)
        self.assertIn('already owns', output)
        self.assertEqual(SiteConfig.objects.get().deck_owner, owner)

    def test_change__ownerless_deck_raises_the_callers_error_channel(self):
        """A deck whose SiteConfig has no owner (defensive: the field is NOT
        NULL) surfaces as the ValueError/CommandError the callers already handle,
        never an AttributeError on the missing owner (review find)."""
        from unittest.mock import Mock, patch

        from django.core.management.base import CommandError

        baker.make(User, is_staff=True, username='wouldbe')
        with patch('tenant.utils.SiteConfig.get', return_value=Mock(deck_owner=None)):
            with self.assertRaisesMessage(CommandError, 'no owner set in its SiteConfig'):
                self.run_command(self.tenant.schema_name, 'wouldbe')

    def test_change__rejects_non_staff_unknown_user_and_non_deck_schemas(self):
        """A non-staff user, an unknown username, an unknown schema, and the
        public schema (not a deck) each fail loudly with the owner unchanged."""
        from django.core.management.base import CommandError

        owner = SiteConfig.get().deck_owner
        baker.make(User, is_staff=False, username='student')

        with self.assertRaises(CommandError):
            self.run_command(self.tenant.schema_name, 'student')
        with self.assertRaises(CommandError):
            self.run_command(self.tenant.schema_name, 'no_such_user')
        with self.assertRaises(CommandError):
            self.run_command('no_such_deck', 'whoever')
        with self.assertRaises(CommandError):
            self.run_command(get_public_schema_name(), 'whoever')
        self.assertEqual(SiteConfig.objects.get().deck_owner, owner)
