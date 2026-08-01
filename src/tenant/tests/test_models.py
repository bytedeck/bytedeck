from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from django_tenants.utils import get_public_schema_name, schema_context
from freezegun import freeze_time
from model_bakery import baker
from hackerspace_online import settings
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

from tenant.models import (
    EXPIRY_WARNING_DAYS, GRACE_PERIOD_DAYS, TRIAL_MAX_ACTIVE_USERS, DeckNotice, Tenant, check_tenant_name, default_trial_end_date,
)

User = get_user_model()


class TenantModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Build an extra tenant on a localhost domain to exercise dev-domain behavior."""
        # TenantTestCase comes with a `cls.tenant` already, but let make another so we can test development
        # stuff on localhost domain
        with schema_context(get_public_schema_name()):
            cls.tenant_localhost = Tenant(
                schema_name='my_development_schema',
                name='my_name'
            )
            cls.tenant_localhost.save()
            domain = cls.tenant_localhost.get_primary_domain()
            domain.domain = 'my-dev-schema.localhost'
            domain.save()

    def test_tenant_test_case__provides_configured_tenant(self):
        """ From docs: https://django-tenant-schemas.readthedocs.io/en/latest/test.html
        If you want a test to happen at any of the tenant’s domain, you can use the test case TenantTestCase.
        It will automatically create a tenant for you, set the connection’s schema to tenant’s schema and
        make it available at `self.tenant`
        """
        self.assertIsInstance(self.tenant, Tenant)
        self.assertEqual(self.tenant.schema_name, 'test')
        self.assertEqual(str(self.tenant), f'{self.tenant.schema_name} - {self.tenant.primary_domain_url}')

    def test_tenant_creation__localhost_tenant_created(self):
        """A tenant created on a localhost domain is a valid Tenant instance."""
        self.assertIsInstance(self.tenant_localhost, Tenant)

    def test_get_root_url__https_and_localhost(self):
        """get_root_url returns an https URL for a real domain and an http localhost URL for a dev tenant."""
        self.assertEqual(self.tenant.get_root_url(), "https://tenant.test.com")
        self.assertEqual(self.tenant_localhost.get_root_url(), "http://my-dev-schema.localhost:8000")

    def test_last_staff_login__populated_excluding_admin(self):
        """ When a staff logins to a tenant, the last_staff_login should have the correct value,
        should not include the admin account
        """
        self.assertIsNone(self.tenant.last_staff_login)

        staff = baker.make(User, is_staff=True)
        self.client.force_login(staff)
        self.tenant.update_cached_fields()

        staff.refresh_from_db()
        self.assertIsNotNone(self.tenant.last_staff_login)
        self.assertEqual(self.tenant.last_staff_login, staff.last_login)

        # if admin account logs in, should not change the result
        admin = User.objects.get(username=settings.TENANT_DEFAULT_ADMIN_USERNAME)
        self.client.force_login(admin)
        self.tenant.update_cached_fields()
        admin.refresh_from_db()
        # should still return the staff user's last log in, ignoring the admin user
        self.assertEqual(self.tenant.last_staff_login, staff.last_login)


class CheckTenantNameTest(SimpleTestCase):
    """ A tenant's name is used for both the schema_name and as the subdomain in the
    tenant's domain_url field, so {name} it must be valid for a schema and a url.
    """

    def test_check_tenant_name__underscore_invalid(self):
        """A name containing underscores is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, 'tenant_name_with_underscores')

    def test_check_tenant_name__special_chars_invalid(self):
        """A name containing special characters is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, 'tenant@')

    def test_check_tenant_name__number_start_invalid(self):
        """A name starting with a number is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, '9tenant')

    def test_check_tenant_name__uppercase_invalid(self):
        """A name containing uppercase letters (after the first character) is rejected.

        The mid-string capital matters: a leading capital trips the must-start-lowercase
        check instead, leaving the capital-letter branch untested.
        """
        self.assertRaises(ValidationError, check_tenant_name, 'tEnant')

    def test_check_tenant_name__start_dash_invalid(self):
        """A name starting with a dash is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, '-tenant')

    def test_check_tenant_name__end_dash_invalid(self):
        """A name ending with a dash is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, 'tenant-')

    def test_check_tenant_name__multidash_invalid(self):
        """A name with consecutive dashes is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, 'ten--ant')

    def test_check_tenant_name__mid_dash_valid(self):
        """A name with a single mid-string dash is accepted."""
        check_tenant_name('ten-ant')

    def test_check_tenant_name__multi_mid_dash_valid(self):
        """A name with multiple non-consecutive mid-string dashes is accepted."""
        check_tenant_name('ten-an-t')

    def test_check_tenant_name__mid_number_valid(self):
        """A name with numbers after the first character is accepted."""
        check_tenant_name('t3nan4')


# Today, as frozen for every billing-status test below. The clock is frozen at
# midday UTC so that timezone.localdate() (which the properties use, computed in
# settings.TIME_ZONE = America/Vancouver) still falls on this same calendar date.
FROZEN_TODAY = date(2026, 8, 15)
FROZEN_NOW = "2026-08-15 20:00:00"


@freeze_time(FROZEN_NOW)
class TenantBillingStatusTest(SimpleTestCase):
    """Tests for the derived billing/lifecycle status properties on Tenant (epic #1729).

    The properties are pure date logic, so they are exercised on unsaved in-memory
    instances with today frozen at FROZEN_TODAY -- no database needed.
    """

    def make_tenant(self, trial_end_date=None, paid_until=None, max_active_users=5):
        """Build an unsaved Tenant with explicit billing dates (overriding field defaults)."""
        return Tenant(name='statustest', trial_end_date=trial_end_date, paid_until=paid_until, max_active_users=max_active_users)

    def test_subscription_active__true_through_paid_until(self):
        """A deck is subscription_active on and before its paid_until date."""
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY).subscription_active)
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY + timedelta(days=90)).subscription_active)

    def test_subscription_active__true_within_grace_period(self):
        """A deck stays subscription_active up to GRACE_PERIOD_DAYS past paid_until."""
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS)).subscription_active)

    def test_subscription_active__false_after_grace_period(self):
        """A deck is no longer subscription_active once the grace period has fully lapsed."""
        self.assertFalse(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1)).subscription_active)

    def test_subscription_active__false_when_paid_until_blank(self):
        """A deck with no paid_until has no subscription, regardless of its trial date."""
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY + timedelta(days=30)).subscription_active)

    def test_grace_days_remaining__counts_down_through_the_grace_window(self):
        """Days of grace left after paid_until: GRACE_PERIOD_DAYS minus the days
        elapsed, 0 on the final grace day, and None for any deck not in grace
        (still paid, on trial, suspended, or unmanaged)."""
        self.assertEqual(
            self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=10)).grace_days_remaining, GRACE_PERIOD_DAYS - 10)
        self.assertEqual(
            self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS)).grace_days_remaining, 0)
        self.assertIsNone(self.make_tenant(paid_until=FROZEN_TODAY + timedelta(days=90)).grace_days_remaining)  # still paid
        self.assertIsNone(self.make_tenant(trial_end_date=FROZEN_TODAY + timedelta(days=30)).grace_days_remaining)  # trial
        self.assertIsNone(
            self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1)).grace_days_remaining)  # suspended
        self.assertIsNone(self.make_tenant().grace_days_remaining)  # unmanaged

    def test_in_grace_period__only_between_paid_until_and_grace_end(self):
        """in_grace_period is True strictly after paid_until and only while subscription_active."""
        self.assertFalse(self.make_tenant(paid_until=FROZEN_TODAY).in_grace_period)
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=1)).in_grace_period)
        self.assertFalse(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1)).in_grace_period)

    def test_is_on_trial__true_through_trial_end_date(self):
        """A deck with no subscription is on trial through its trial_end_date."""
        self.assertTrue(self.make_tenant(trial_end_date=FROZEN_TODAY).is_on_trial)
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1)).is_on_trial)

    def test_is_on_trial__false_when_subscribed_or_dateless(self):
        """An active subscription (or no trial date at all) means the deck is not on trial."""
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY + timedelta(days=30), paid_until=FROZEN_TODAY).is_on_trial)
        self.assertFalse(self.make_tenant().is_on_trial)

    def test_is_suspended__true_when_all_given_clocks_lapsed(self):
        """A deck whose trial and/or paid clocks have all run out (past grace) is suspended."""
        self.assertTrue(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1)).is_suspended)
        # trial date cleared by an admin, paid_until lapsed beyond grace: still suspended
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1)).is_suspended)
        self.assertTrue(
            self.make_tenant(
                trial_end_date=FROZEN_TODAY - timedelta(days=100),
                paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1),
            ).is_suspended
        )

    def test_is_suspended__false_when_active_trialing_or_unmanaged(self):
        """Subscribed, on-trial, and dateless (comped/legacy) decks are never suspended."""
        self.assertFalse(self.make_tenant(paid_until=FROZEN_TODAY).is_suspended)
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY).is_suspended)
        self.assertFalse(self.make_tenant().is_suspended)

    def test_effective_max_active_users__subscribed_uses_field_value(self):
        """An actively subscribed deck's cap is its max_active_users field."""
        self.assertEqual(self.make_tenant(paid_until=FROZEN_TODAY, max_active_users=80).effective_max_active_users, 80)

    def test_effective_max_active_users__always_the_admin_field(self):
        """The enforced cap is ALWAYS the admin-set field, in every billing state --
        including suspended. Suspension "reverts to trial limits" by WRITING the
        trial default into the field once (reset_cap_on_new_suspension), after
        which the admin's value, higher or lower, always wins (maintainer decision
        on #2178: a suspended deck's cap lowered to 1 was silently overridden back
        to 5)."""
        # suspended (trial lapsed): the field, untouched at read time -- both above
        # and below the trial default (the 80 only drops when the nightly reset runs)
        self.assertEqual(
            self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1), max_active_users=80).effective_max_active_users, 80,
        )
        self.assertEqual(
            self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1), max_active_users=1).effective_max_active_users, 1,
        )
        # on trial with an admin-raised cap: the admin grant is honored
        self.assertEqual(
            self.make_tenant(trial_end_date=FROZEN_TODAY, max_active_users=80).effective_max_active_users, 80,
        )
        # managed manually (no dates at all): the admin-set cap is honored
        self.assertEqual(self.make_tenant(max_active_users=40).effective_max_active_users, 40)

    def test_is_on_maintenance__paid_at_or_below_trial_cap(self):
        """A deck paying for a subscription that leaves the cap at (or below) the
        trial limit is on MAINTENANCE: alive (never suspends or times out for
        deletion) but capped. Higher caps are real subscriptions; unlimited (-1)
        is never maintenance; unpaid states never are."""
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY, max_active_users=TRIAL_MAX_ACTIVE_USERS).is_on_maintenance)
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY, max_active_users=1).is_on_maintenance)
        # grace still counts as paid, so a lapsing maintenance deck keeps the flag
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=5), max_active_users=5).is_on_maintenance)
        self.assertFalse(self.make_tenant(paid_until=FROZEN_TODAY, max_active_users=6).is_on_maintenance)
        self.assertFalse(self.make_tenant(paid_until=FROZEN_TODAY, max_active_users=-1).is_on_maintenance)
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY, max_active_users=5).is_on_maintenance)  # trial
        self.assertFalse(self.make_tenant(max_active_users=5).is_on_maintenance)  # managed manually
        self.assertFalse(  # suspended
            self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1), max_active_users=5).is_on_maintenance
        )

    def test_effective_max_active_users__unlimited_passthrough(self):
        """The admin-set unlimited sentinel (-1) is honored in every state."""
        self.assertEqual(self.make_tenant(max_active_users=-1).effective_max_active_users, -1)
        self.assertEqual(
            self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1), max_active_users=-1).effective_max_active_users,
            -1,
        )

    def test_days_until_expiry__counts_down_to_governing_deadline(self):
        """days_until_expiry counts down to paid_until when subscribed, else trial_end_date."""
        self.assertEqual(self.make_tenant(paid_until=FROZEN_TODAY + timedelta(days=10)).days_until_expiry, 10)
        self.assertEqual(self.make_tenant(trial_end_date=FROZEN_TODAY + timedelta(days=3)).days_until_expiry, 3)

    def test_days_until_expiry__negative_after_deadline_and_none_when_unmanaged(self):
        """days_until_expiry goes negative once the deadline passes (feeding the grace-window
        reminder cadence), falls back to a lapsed paid_until when the trial date is cleared,
        and is None for dateless decks."""
        self.assertEqual(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=2)).days_until_expiry, -2)
        self.assertEqual(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=5)).days_until_expiry, -5)
        self.assertEqual(
            self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 10)).days_until_expiry,
            -(GRACE_PERIOD_DAYS + 10),
        )
        self.assertIsNone(self.make_tenant().days_until_expiry)

    def test_days_until_expiry__suspended_deck_uses_latest_lapsed_clock(self):
        """A lapsed ex-subscriber that still carries its ancient (never-cleared) trial date
        reports expiry relative to the more recent paid_until, not the trial date."""
        tenant = self.make_tenant(
            trial_end_date=FROZEN_TODAY - timedelta(days=400),
            paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 5),
        )
        self.assertTrue(tenant.is_suspended)
        self.assertEqual(tenant.days_until_expiry, -(GRACE_PERIOD_DAYS + 5))


class TenantCountingAndCachingTest(ByteDeckTenantTestCase):
    """Tests for the Tenant counting fix and cached-field save behavior (epic #1729 PR 1).

    Counting: staff who are also enrolled in a course are counted once, and enrolled
    (non-staff) test accounts never count -- the first two tests fail without the
    students_only=True fix. Caching: update_cached_fields must not clobber concurrent
    edits to non-cached columns.
    """

    def test_get_active_user_count__counts_enrolled_students_only(self):
        """Only students registered in a course in the active semester count; an
        unregistered student does not."""
        baseline = self.tenant.get_active_user_count()
        enrolled = baker.make(User)
        baker.make('courses.CourseStudent', user=enrolled, semester=SiteConfig.get().active_semester)
        baker.make(User)  # signed up but never registered in a course
        self.assertEqual(self.tenant.get_active_user_count(), baseline + 1)

    def test_get_active_user_count__staff_and_superusers_never_count(self):
        """Staff and superusers don't consume seats, whether or not they're registered
        in a course -- pricing is based on active students only."""
        baseline = self.tenant.get_active_user_count()
        staff = baker.make(User, is_staff=True)
        baker.make('courses.CourseStudent', user=staff, semester=SiteConfig.get().active_semester)
        superuser = baker.make(User, is_superuser=True, is_staff=False)
        baker.make('courses.CourseStudent', user=superuser, semester=SiteConfig.get().active_semester)
        baker.make(User, is_staff=True)  # unenrolled staff
        self.assertEqual(self.tenant.get_active_user_count(), baseline)

    def test_get_active_user_count__test_accounts_excluded(self):
        """An enrolled test account does not count toward the active-user total."""
        baseline = self.tenant.get_active_user_count()
        student = baker.make(User)
        student.profile.is_test_account = True
        student.profile.save()
        baker.make('courses.CourseStudent', user=student, semester=SiteConfig.get().active_semester)
        self.assertEqual(self.tenant.get_active_user_count(), baseline)

    def test_get_active_user_count__archived_students_excluded(self):
        """An enrolled student who is archived (is_active=False) stops counting --
        archiving users is the documented way to get back under the cap (#1733)."""
        baseline = self.tenant.get_active_user_count()
        student = baker.make(User)
        baker.make('courses.CourseStudent', user=student, semester=SiteConfig.get().active_semester)
        self.assertEqual(self.tenant.get_active_user_count(), baseline + 1)
        student.is_active = False
        student.save()
        self.assertEqual(self.tenant.get_active_user_count(), baseline)

    def test_update_cached_fields__does_not_clobber_concurrent_edits(self):
        """A stale instance running update_cached_fields must not overwrite a concurrent
        edit to a non-cached column such as paid_until."""
        stale = Tenant.objects.get(pk=self.tenant.pk)
        Tenant.objects.filter(pk=self.tenant.pk).update(paid_until=date(2030, 1, 1))
        stale.update_cached_fields()
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.paid_until, date(2030, 1, 1))

    def test_is_over_user_limit__compares_live_count_to_effective_cap(self):
        """Over-limit only when the LIVE current-student count exceeds the effective
        cap -- the nightly-cached field is ignored (production find: a stale cached
        count made the banner disagree with the live student list)."""
        from django.utils.timezone import localdate

        baseline = self.tenant.get_active_user_count()
        for _ in range(2):
            baker.make('courses.CourseStudent', user=baker.make(User), active=True,
                       semester=SiteConfig.get().active_semester)
        live = baseline + 2

        # cached count deliberately left stale at 0 in every case: it must not matter
        def deck(**fields):
            Tenant.objects.filter(pk=self.tenant.pk).update(active_user_count=0, **fields)
            return Tenant.objects.get(pk=self.tenant.pk)

        self.assertTrue(deck(trial_end_date=localdate(), max_active_users=live - 1).is_over_user_limit)
        self.assertFalse(deck(max_active_users=live).is_over_user_limit)  # at the cap is not over it
        # subscribed deck uses its own (tier) cap, not the trial cap
        self.assertFalse(deck(paid_until=localdate(), max_active_users=40).is_over_user_limit)
        self.assertTrue(deck(paid_until=localdate(), max_active_users=live - 1).is_over_user_limit)
class OwnerEmailResolutionTest(ByteDeckTenantTestCase):
    """Tests for Tenant.get_owner_email_cached() owner-email resolution (#1729 rollout).

    Legacy deck owners often predate the allauth sign-up flows, so they have a
    User.email but no EmailAddress bookkeeping row; the resolver must still
    surface their address, because the notice engine, checkout prefill, and the
    Stripe backfill report's matching all ride on it.
    """

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

    def test_get_owner_email_cached__resolves_without_an_emailaddress_row(self):
        """An owner with a plain User.email but no allauth EmailAddress row still
        resolves to that address: a missing bookkeeping row must not silently
        disable every owner email for a legacy deck."""
        self.set_owner(email='legacy.owner@example.com')
        self.assertEqual(self.tenant.get_owner_email_cached(), 'legacy.owner@example.com')

    def test_get_owner_email_cached__none_when_owner_has_no_email(self):
        """An owner with no email at all resolves to None: the notice engine then
        skips the email leg, and the backfill command reports the deck for a
        human to fix in the SiteConfig admin."""
        self.set_owner(email='')
        self.assertIsNone(self.tenant.get_owner_email_cached())


class DefaultTrialEndDateTest(SimpleTestCase):
    """Tests for the default demo/trial expiry date on new tenants (Issue #1146).

    A new deck's trial runs for 60 days, so ``Tenant.trial_end_date`` defaults to
    ``today + 60 days``. Time is frozen so "today" is deterministic.
    """

    @freeze_time("2024-02-29")  # a leap day, so the +60 arithmetic can't be faked with month math
    def test_default_trial_end_date__is_60_days_from_today(self):
        """The default_trial_end_date() helper returns exactly 60 days from today."""
        self.assertEqual(default_trial_end_date(), date(2024, 2, 29) + timedelta(days=60))

    @freeze_time("2024-02-29")
    def test_new_tenant__trial_end_date_defaults_to_60_days_out(self):
        """A newly built Tenant gets trial_end_date defaulted to today + 60 days."""
        # Field defaults are applied at instantiation, so no save() (and no DB) is needed.
        tenant = Tenant(schema_name="demo", name="demo")
        self.assertEqual(tenant.trial_end_date, date(2024, 2, 29) + timedelta(days=60))


@freeze_time(FROZEN_NOW)
class TenantBannerStatusTest(SimpleTestCase):
    """Tests for the banner-support properties is_over_user_limit and is_expiring_soon
    (epic #1729 PR 3), on unsaved in-memory instances with today frozen at FROZEN_TODAY."""

    def make_tenant(self, trial_end_date=None, paid_until=None, max_active_users=5, active_user_count=0):
        """Build an unsaved Tenant with the given billing dates and cached count."""
        return Tenant(
            name='bannertest', trial_end_date=trial_end_date, paid_until=paid_until,
            max_active_users=max_active_users, active_user_count=active_user_count,
        )

    def test_is_over_user_limit__unlimited_short_circuits_without_querying(self):
        """An unlimited (-1) deck is never over its limit -- and the check must not
        touch the database at all (this SimpleTestCase would raise on any query),
        since the live recount is skipped entirely by the -1 short-circuit."""
        self.assertFalse(self.make_tenant(max_active_users=-1, active_user_count=999).is_over_user_limit)

    def test_is_expiring_soon__within_warning_window_or_grace(self):
        """Warns within EXPIRY_WARNING_DAYS of the governing deadline, and through the
        paid grace window (negative days); quiet before the window."""
        self.assertTrue(self.make_tenant(trial_end_date=FROZEN_TODAY + timedelta(days=EXPIRY_WARNING_DAYS)).is_expiring_soon)
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY + timedelta(days=EXPIRY_WARNING_DAYS + 1)).is_expiring_soon)
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY + timedelta(days=3)).is_expiring_soon)
        # in the paid grace window: expired but still subscription_active
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=5)).is_expiring_soon)

    def test_is_expiring_soon__false_for_suspended_and_unmanaged_decks(self):
        """Suspended decks get the suspension banner instead, and dateless (comped)
        decks have no deadline to warn about."""
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1)).is_expiring_soon)
        self.assertFalse(self.make_tenant().is_expiring_soon)


class DeckNoticeModelTest(ByteDeckTenantTestCase):
    """Tests for the DeckNotice reminder ledger model (epic #1729 PR 5, #1733)."""

    def test_str__identifies_deck_kind_threshold_and_period(self):
        """The string form names the deck schema, kind/threshold, and period key."""
        notice = DeckNotice.objects.create(
            tenant=self.tenant, kind=DeckNotice.KIND_LIMIT, threshold='pct80', period_key='2026-08'
        )
        self.assertEqual(str(notice), f'{self.tenant.schema_name}: limit/pct80 for 2026-08')
