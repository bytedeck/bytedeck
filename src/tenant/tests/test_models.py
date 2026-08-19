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
    EXPIRY_WARNING_DAYS, GRACE_PERIOD_DAYS, INACTIVE_DELETE_DAYS, TRIAL_MAX_ACTIVE_USERS, DeckNotice, Tenant, check_tenant_name,
    default_trial_end_date,
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
        """in_grace_period is True strictly after paid_until and only until the grace window closes."""
        self.assertFalse(self.make_tenant(paid_until=FROZEN_TODAY).in_grace_period)
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=1)).in_grace_period)
        self.assertFalse(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1)).in_grace_period)

    def test_in_grace_period__lapsed_trial_gets_the_same_grace(self):
        """A lapsed trial enters the SAME grace window a lapsed subscription gets
        (#1734 B4: a trial is just another kind of subscription): grace starts the
        day after trial_end_date, runs GRACE_PERIOD_DAYS, then closes."""
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY).in_grace_period)  # still on trial
        self.assertTrue(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1)).in_grace_period)
        self.assertTrue(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS)).in_grace_period)
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1)).in_grace_period)

    def test_grace_days_remaining__lapsed_trial_counts_down_too(self):
        """The grace countdown works identically for a lapsed trial (#1734 B4)."""
        self.assertEqual(
            self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=10)).grace_days_remaining, GRACE_PERIOD_DAYS - 10)
        self.assertEqual(
            self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS)).grace_days_remaining, 0)

    def test_suspended_since__day_after_the_last_covered_day(self):
        """suspended_since is the day after the deck's last covered day: the close of
        the unified grace window after the LATEST clock, trial or paid alike
        (#1734 B4); None while not suspended."""
        lapsed_trial = FROZEN_TODAY - timedelta(days=100)
        lapsed_paid = FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 10)

        self.assertIsNone(self.make_tenant(paid_until=FROZEN_TODAY).suspended_since)  # subscribed
        self.assertIsNone(self.make_tenant(trial_end_date=FROZEN_TODAY).suspended_since)  # on trial
        self.assertIsNone(self.make_tenant().suspended_since)  # managed manually

        self.assertEqual(
            self.make_tenant(trial_end_date=lapsed_trial).suspended_since,
            lapsed_trial + timedelta(days=GRACE_PERIOD_DAYS + 1))
        self.assertEqual(
            self.make_tenant(paid_until=lapsed_paid).suspended_since,
            lapsed_paid + timedelta(days=GRACE_PERIOD_DAYS + 1))
        # both dates: the LATER covered day governs (an ancient trial date must not
        # backdate a lapsed subscriber's suspension)
        self.assertEqual(
            self.make_tenant(trial_end_date=lapsed_trial, paid_until=lapsed_paid).suspended_since,
            lapsed_paid + timedelta(days=GRACE_PERIOD_DAYS + 1))

    def test_governing_deadline_and_origin__latest_clock_wins(self):
        """governing_deadline is the LATEST set clock (None for dateless decks) and
        governing_clock_is_trial says which clock it is, preferring subscription
        language on a tie: presentation keys its trial-vs-paid wording off these
        rather than off paid_until existing (#1734 B4 review find: an
        admin-extended trial can outlast an old lapsed paid date)."""
        trial_later = self.make_tenant(
            trial_end_date=FROZEN_TODAY - timedelta(days=5), paid_until=FROZEN_TODAY - timedelta(days=100))
        self.assertEqual(trial_later.governing_deadline, FROZEN_TODAY - timedelta(days=5))
        self.assertTrue(trial_later.governing_clock_is_trial)

        paid_later = self.make_tenant(
            trial_end_date=FROZEN_TODAY - timedelta(days=100), paid_until=FROZEN_TODAY + timedelta(days=5))
        self.assertEqual(paid_later.governing_deadline, FROZEN_TODAY + timedelta(days=5))
        self.assertFalse(paid_later.governing_clock_is_trial)

        # a tie speaks subscription language
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY, paid_until=FROZEN_TODAY).governing_clock_is_trial)

        self.assertTrue(self.make_tenant(trial_end_date=FROZEN_TODAY).governing_clock_is_trial)  # trial-only
        self.assertIsNone(self.make_tenant().governing_deadline)  # managed manually
        self.assertFalse(self.make_tenant().governing_clock_is_trial)

    def test_is_on_trial__true_through_trial_end_date(self):
        """A deck with no subscription is on trial through its trial_end_date."""
        self.assertTrue(self.make_tenant(trial_end_date=FROZEN_TODAY).is_on_trial)
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1)).is_on_trial)

    def test_is_on_trial__false_when_subscribed_or_dateless(self):
        """An active subscription (or no trial date at all) means the deck is not on trial."""
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY + timedelta(days=30), paid_until=FROZEN_TODAY).is_on_trial)
        self.assertFalse(self.make_tenant().is_on_trial)

    def test_is_suspended__true_when_all_given_clocks_lapsed(self):
        """A deck whose trial and/or paid clocks have all run out past the unified
        grace window is suspended; a just-lapsed trial is still in grace (#1734 B4)."""
        self.assertTrue(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1)).is_suspended)
        # a lapsed trial inside its grace window is NOT yet suspended
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1)).is_suspended)
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS)).is_suspended)
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
        including suspended. Suspension never touches the cap (#1734 redesign:
        owner-only sign-in instead); the admin's value, higher or lower, always
        wins (maintainer decision on #2178: a suspended deck's cap lowered to 1
        was silently overridden back to 5)."""
        # suspended (trial lapsed past grace): the field, untouched -- both above
        # and below the trial default
        self.assertEqual(
            self.make_tenant(
                trial_end_date=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1), max_active_users=80,
            ).effective_max_active_users, 80,
        )
        self.assertEqual(
            self.make_tenant(
                trial_end_date=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1), max_active_users=1,
            ).effective_max_active_users, 1,
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
        self.assertFalse(  # suspended (trial lapsed past grace)
            self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1), max_active_users=5).is_on_maintenance
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

    def test_subscription_status__one_slug_per_lifecycle_state(self):
        """subscription_status maps each lifecycle state to its slug: the single
        precedence chain behind the subscription page badge and the admin's
        Subscription column."""
        self.assertEqual(self.make_tenant().subscription_status, 'manual')
        self.assertEqual(self.make_tenant(trial_end_date=FROZEN_TODAY).subscription_status, 'trial')
        self.assertEqual(self.make_tenant(paid_until=FROZEN_TODAY, max_active_users=40).subscription_status, 'subscribed')
        self.assertEqual(
            self.make_tenant(paid_until=FROZEN_TODAY, max_active_users=TRIAL_MAX_ACTIVE_USERS).subscription_status, 'maintenance')
        self.assertEqual(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1)).subscription_status, 'grace')
        self.assertEqual(
            self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1), max_active_users=40).subscription_status,
            'suspended')

    def test_subscription_status__precedence_when_states_overlap(self):
        """Where the underlying properties overlap, the more urgent state wins:
        a deck in the paid clock's grace window is 'grace' even though
        subscription_active (and the maintenance cap test) still hold there, and
        a suspended deck is 'suspended' even though its old trial date still
        exists. Unlimited (-1) paid decks are 'subscribed', never 'maintenance'."""
        # paid grace: subscription_active is still True through the window, grace wins
        self.assertEqual(
            self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=1), max_active_users=40).subscription_status, 'grace')
        # a lapsing maintenance deck in grace is 'grace' too, not 'maintenance'
        self.assertEqual(
            self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=1), max_active_users=TRIAL_MAX_ACTIVE_USERS).subscription_status,
            'grace')
        # suspension outranks the stale never-cleared trial date
        self.assertEqual(
            self.make_tenant(
                trial_end_date=FROZEN_TODAY - timedelta(days=400),
                paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 5),
            ).subscription_status,
            'suspended')
        # unlimited seats is a real subscription, not maintenance
        self.assertEqual(self.make_tenant(paid_until=FROZEN_TODAY, max_active_users=-1).subscription_status, 'subscribed')
        # the GOVERNING (latest) clock decides trial vs paid (#1734 B4): an
        # admin-extended trial outranks an older paid_until even while that paid
        # date's grace tail keeps subscription_active True (regression: this
        # deck read as 'subscribed'/'maintenance' when only the paid flags were
        # consulted), and also while the paid date is still current
        self.assertEqual(
            self.make_tenant(
                trial_end_date=FROZEN_TODAY + timedelta(days=30), paid_until=FROZEN_TODAY - timedelta(days=1),
                max_active_users=40,
            ).subscription_status,
            'trial')
        self.assertEqual(
            self.make_tenant(
                trial_end_date=FROZEN_TODAY + timedelta(days=60), paid_until=FROZEN_TODAY + timedelta(days=30),
            ).subscription_status,
            'trial')
        # a TIE between the clocks speaks subscription language (B4)
        self.assertEqual(
            self.make_tenant(
                trial_end_date=FROZEN_TODAY + timedelta(days=30), paid_until=FROZEN_TODAY + timedelta(days=30),
                max_active_users=40,
            ).subscription_status,
            'subscribed')

    def test_subscription_status_label__human_label_for_every_slug(self):
        """subscription_status_label renders the human word for the current slug,
        for a deck in each of the six lifecycle states, and the label map holds
        exactly those six labels (a typo in any one label fails here)."""
        self.assertEqual(self.make_tenant().subscription_status_label, 'Managed manually')
        self.assertEqual(self.make_tenant(trial_end_date=FROZEN_TODAY).subscription_status_label, 'Free trial')
        self.assertEqual(
            self.make_tenant(paid_until=FROZEN_TODAY, max_active_users=40).subscription_status_label, 'Subscribed')
        self.assertEqual(
            self.make_tenant(paid_until=FROZEN_TODAY, max_active_users=TRIAL_MAX_ACTIVE_USERS).subscription_status_label,
            'Maintenance')
        self.assertEqual(
            self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=1)).subscription_status_label, 'Grace period')
        self.assertEqual(
            self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1)).subscription_status_label,
            'Suspended')
        self.assertEqual(
            Tenant.SUBSCRIPTION_STATUS_LABELS,
            {
                'suspended': 'Suspended',
                'grace': 'Grace period',
                'maintenance': 'Maintenance',
                'subscribed': 'Subscribed',
                'trial': 'Free trial',
                'manual': 'Managed manually',
            })


@freeze_time(FROZEN_NOW)
class TenantDeletionClockTest(ByteDeckTenantTestCase):
    """Tests for the suspension-keyed deletion clock (#1734 B3): Tenant.deletion_date
    and the is_deletable guard it drives.

    The deletion day is INACTIVE_DELETE_DAYS after the LATER of the suspension
    start and the episode's first suspended notice, so a legacy deck suspended
    long before the notice machinery went live still gets the full year the
    warning email promised. Needs the database: the first-warned lookup reads
    the DeckNotice ledger, so these run on the saved test tenant.
    """

    LAPSED_TRIAL = FROZEN_TODAY - timedelta(days=800)  # suspended long ago; no paid date

    def deck(self, **overrides):
        """Return this test's Tenant row re-fetched with the given field values applied.

        Args:
            **overrides: Tenant field values; defaults make the deck suspended via
                a long-lapsed trial and armed for deletion.

        Returns:
            Tenant: A fresh instance reflecting the applied fields.
        """
        fields = {
            'trial_end_date': self.LAPSED_TRIAL, 'paid_until': None, 'can_delete': True,
            'deletion_requested_on': None,  # each test states its own request explicitly
        }
        fields.update(overrides)
        Tenant.objects.filter(pk=self.tenant.pk).update(**fields)
        return Tenant.objects.get(pk=self.tenant.pk)

    def warn(self, days_ago, period_key=None):
        """Record the deck's suspended notice as sent `days_ago` days ago.

        Args:
            days_ago (int): How many days before the frozen today the warning went out.
            period_key (str): Ledger episode key; defaults to this test's lapsed
                trial date, the key the notice engine writes for that episode.

        Returns:
            DeckNotice: The (backdated) ledger row.
        """
        notice = DeckNotice.objects.create(
            tenant=self.tenant, kind=DeckNotice.KIND_SUSPENDED, threshold='suspended',
            period_key=period_key or str(self.LAPSED_TRIAL))
        # backdate past auto_now_add: the ledger records when the warning really went out
        DeckNotice.objects.filter(pk=notice.pk).update(sent_on=FROZEN_TODAY - timedelta(days=days_ago))
        return notice

    def test_deletion_eligibility__names_the_path_or_none(self):
        """The eligibility chain behind is_deletable and the admin's "deletable"
        column: 'request' for a suspended deck with a standing owner request
        (outranking the clock), 'timeout' once the year has run, None while the
        deck is live, unwarned, or mid-clock. Arming can_delete is deliberately
        NOT part of eligibility (it is the operator's remaining step)."""
        # suspended with a standing request: 'request', armed or not
        self.assertEqual(
            self.deck(deletion_requested_on=FROZEN_TODAY, can_delete=False).deletion_eligibility, 'request')
        # suspended, warned over a year ago: 'timeout'
        self.warn(days_ago=INACTIVE_DELETE_DAYS + 1)
        self.assertEqual(self.deck().deletion_eligibility, 'timeout')
        # a request outranks (and out-labels) the elapsed clock
        self.assertEqual(self.deck(deletion_requested_on=FROZEN_TODAY).deletion_eligibility, 'request')
        # live deck: never eligible, request or not
        self.assertIsNone(self.deck(
            trial_end_date=FROZEN_TODAY + timedelta(days=30),
            deletion_requested_on=FROZEN_TODAY).deletion_eligibility)

    def test_is_deletable__owner_request_skips_the_year_clock(self):
        """A suspended, armed deck whose owner has a standing deletion request is
        deletable immediately: the request plus the operator arming can_delete
        stand in for the year clock (#2330). The request alone changes nothing
        on a deck that is not suspended or not armed, and without a request the
        same deck still waits out its year."""
        self.warn(days_ago=10)  # the year clock started 10 days ago: nowhere near up
        self.assertTrue(self.deck(deletion_requested_on=FROZEN_TODAY - timedelta(days=1)).is_deletable)
        # same deck, no request: the year clock still governs
        self.assertFalse(self.deck().is_deletable)
        # a live deck is never deletable, request or not (the operator can
        # suspend it first by editing its dates)
        self.assertFalse(self.deck(
            trial_end_date=FROZEN_TODAY + timedelta(days=30),
            deletion_requested_on=FROZEN_TODAY).is_deletable)
        # unarmed: the request is advisory until an operator reviews it
        self.assertFalse(self.deck(can_delete=False, deletion_requested_on=FROZEN_TODAY).is_deletable)

    def test_deletion_date__none_while_not_suspended(self):
        """An active, on-trial, or managed-manually deck has no deletion date."""
        self.assertIsNone(self.deck(trial_end_date=FROZEN_TODAY + timedelta(days=10)).deletion_date)
        self.assertIsNone(self.deck(trial_end_date=None).deletion_date)  # managed manually

    def test_deletion_date__clock_unstarted_while_never_warned(self):
        """A suspended deck with no suspended notice on record reads as warned today:
        its deletion date sits the full year out, and it is not deletable no matter
        how long ago its dates lapsed (the legacy-deck protection)."""
        deck = self.deck()
        self.assertEqual(deck.deletion_date, FROZEN_TODAY + timedelta(days=INACTIVE_DELETE_DAYS))
        self.assertFalse(deck.is_deletable)

    def test_deletion_date__counts_from_the_episodes_first_warning(self):
        """A deck suspended long before it was warned counts its year from the first
        suspended notice, never from the backdated lapse."""
        self.warn(days_ago=10)
        deck = self.deck()
        self.assertEqual(deck.deletion_date, FROZEN_TODAY - timedelta(days=10) + timedelta(days=INACTIVE_DELETE_DAYS))
        self.assertFalse(deck.is_deletable)

    def test_deletion_date__old_episodes_warning_does_not_count(self):
        """A suspended notice from a PREVIOUS episode (different period key) does not
        start this episode's clock: a deck that re-subscribed and lapsed again gets
        a fresh year from its new warning."""
        self.warn(days_ago=INACTIVE_DELETE_DAYS + 100, period_key='2020-06-30')
        deck = self.deck()
        self.assertEqual(deck.deletion_date, FROZEN_TODAY + timedelta(days=INACTIVE_DELETE_DAYS))
        self.assertFalse(deck.is_deletable)

    def test_is_deletable__true_once_armed_and_a_year_past_the_first_warning(self):
        """Armed + suspended + the promised year elapsed since the first suspended
        notice: the deck is deletable, starting exactly on its deletion date."""
        self.warn(days_ago=INACTIVE_DELETE_DAYS)
        self.assertTrue(self.deck().is_deletable)

    def test_is_deletable__remaining_protections_still_refuse(self):
        """The other #2044 protections still hold with the clock elapsed: not armed,
        not suspended, and never the public schema."""
        self.warn(days_ago=INACTIVE_DELETE_DAYS + 5)
        self.assertFalse(self.deck(can_delete=False).is_deletable)
        self.assertFalse(self.deck(paid_until=FROZEN_TODAY + timedelta(days=30)).is_deletable)
        # the public schema is never deletable (guarded before any clock math)
        self.assertFalse(Tenant(schema_name='public', can_delete=True).is_deletable)


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

    def test_get_active_user_count__deactivated_registrations_excluded(self):
        """A registration deactivated by a semester close (CourseStudent.active
        False; e.g. the suspension auto-close, #1734 B2) stops counting, so a
        closed semester contributes zero current students."""
        from courses.models import CourseStudent

        baseline = self.tenant.get_active_user_count()
        student = baker.make(User)
        registration = baker.make('courses.CourseStudent', user=student, semester=SiteConfig.get().active_semester)
        self.assertEqual(self.tenant.get_active_user_count(), baseline + 1)
        CourseStudent.objects.filter(pk=registration.pk).update(active=False)
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
        def deck(trial_end_date=None, paid_until=None, **fields):
            # reset both clocks every call: update() is cumulative on the same row, and a
            # leaked date would silently change which billing branch an assertion exercises
            Tenant.objects.filter(pk=self.tenant.pk).update(
                active_user_count=0, trial_end_date=trial_end_date, paid_until=paid_until, **fields)
            return Tenant.objects.get(pk=self.tenant.pk)

        self.assertTrue(deck(trial_end_date=localdate(), max_active_users=live - 1).is_over_user_limit)
        self.assertFalse(deck(trial_end_date=localdate(), max_active_users=live).is_over_user_limit)  # at the cap is not over it
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

    def test_get_owner_email_cached__returns_allauth_canonical_lowercase(self):
        """A mixed-case User.email resolves to allauth's canonical lowercase form
        (user_email lowercases), matching how EmailAddress rows are stored, so
        every consumer of the cache sees one consistent spelling."""
        self.set_owner(email='Mixed.Case@Example.com')
        self.assertEqual(self.tenant.get_owner_email_cached(), 'mixed.case@example.com')

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
        grace window (negative days), paid or trial alike; quiet before the window."""
        self.assertTrue(self.make_tenant(trial_end_date=FROZEN_TODAY + timedelta(days=EXPIRY_WARNING_DAYS)).is_expiring_soon)
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY + timedelta(days=EXPIRY_WARNING_DAYS + 1)).is_expiring_soon)
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY + timedelta(days=3)).is_expiring_soon)
        # in the grace window: expired but not yet suspended (#1734 B4 gives
        # trials the same window)
        self.assertTrue(self.make_tenant(paid_until=FROZEN_TODAY - timedelta(days=5)).is_expiring_soon)
        self.assertTrue(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=5)).is_expiring_soon)

    def test_is_expiring_soon__false_for_suspended_and_unmanaged_decks(self):
        """Suspended decks get the suspension banner instead, and dateless (comped)
        decks have no deadline to warn about."""
        self.assertFalse(self.make_tenant(trial_end_date=FROZEN_TODAY - timedelta(days=GRACE_PERIOD_DAYS + 1)).is_expiring_soon)
        self.assertFalse(self.make_tenant().is_expiring_soon)


class DeckNoticeModelTest(ByteDeckTenantTestCase):
    """Tests for the DeckNotice reminder ledger model (epic #1729 PR 5, #1733)."""

    def test_str__identifies_deck_kind_threshold_and_period(self):
        """The string form names the deck schema, kind/threshold, and period key."""
        notice = DeckNotice.objects.create(
            tenant=self.tenant, kind=DeckNotice.KIND_LIMIT, threshold='pct80', period_key='2026-08'
        )
        self.assertEqual(str(notice), f'{self.tenant.schema_name}: limit/pct80 for 2026-08')


class SyncFromStripeSubscriptionTest(ByteDeckTenantTestCase):
    """Tests for Tenant.sync_from_stripe_subscription -- the single billing write
    path used by every webhook handler, the admin sync action, and the nightly
    reconcile (epic #1729 PR 7, plan §5.2)."""

    # 2027-01-15 12:00 UTC -> 2027-01-15 in America/Vancouver
    PERIOD_END = date(2027, 1, 15)
    PERIOD_END_TS = 1800014400

    def set_deck(self, **fields):
        """Persist billing fields on this deck's Tenant row and refresh the instance."""
        Tenant.objects.filter(pk=self.tenant.pk).update(**fields)
        self.tenant.refresh_from_db()

    def make_subscription(self, **overrides):
        """A minimal Stripe Subscription test double (newer items-based shape)."""
        subscription = {
            'id': 'sub_sync', 'status': 'active', 'customer': 'cus_sync',
            'items': {'data': [{'current_period_end': self.PERIOD_END_TS, 'price': {'id': 'price_x', 'metadata': {}}}]},
        }
        subscription.update(overrides)
        return subscription

    def test_sync__advances_paid_until_and_links_subscription(self):
        """A fresh sync advances paid_until to the period end and links the sub id."""
        self.set_deck(paid_until=None, stripe_subscription_id='')
        summary = self.tenant.sync_from_stripe_subscription(self.make_subscription())
        self.assertIn('paid_until', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.paid_until, self.PERIOD_END)
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_sync')

    def test_sync__monotonic_never_lowers_paid_until(self):
        """A re-delivered or out-of-order older event can never LOWER paid_until."""
        later = self.PERIOD_END + timedelta(days=365)
        self.set_deck(paid_until=later, stripe_subscription_id='sub_sync')
        summary = self.tenant.sync_from_stripe_subscription(self.make_subscription())
        self.assertEqual(summary, 'no changes')
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.paid_until, later)

    def test_sync__stale_instance_cannot_lower_paid_until(self):
        """The monotonic guard is evaluated against the LOCKED database row, not this
        instance's in-memory state: a sync through an instance loaded before a
        concurrent sync advanced paid_until must not lower it back (the stale
        instance reproduces exactly what a lost race between two workers reads)."""
        self.set_deck(paid_until=None, stripe_subscription_id='')
        stale = Tenant.objects.get(pk=self.tenant.pk)  # loaded BEFORE the newer sync

        later_ts = self.PERIOD_END_TS + 100 * 86400
        self.tenant.sync_from_stripe_subscription(self.make_subscription(
            items={'data': [{'current_period_end': later_ts, 'price': {'id': 'price_x', 'metadata': {}}}]},
        ))
        self.tenant.refresh_from_db()
        advanced = self.tenant.paid_until

        # the older event passes the STALE in-memory check (None < older date) but
        # must be rejected against the fresh row
        summary = stale.sync_from_stripe_subscription(self.make_subscription())
        self.assertEqual(summary, 'no changes')
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.paid_until, advanced)

    def test_sync__stale_cancellation_for_other_subscription_ignored(self):
        """A delayed cancellation for a SUPERSEDED subscription (resolved to this
        deck via the customer-id fallback) must not unlink the deck's current
        subscription."""
        self.set_deck(paid_until=self.PERIOD_END, stripe_subscription_id='sub_new')
        summary = self.tenant.sync_from_stripe_subscription(
            self.make_subscription(id='sub_old', status='canceled'))
        self.assertIn('ignored', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_new')

    def test_sync__active_event_for_other_subscription_ignored(self):
        """A delayed ACTIVE event for a superseded subscription must not relink it
        (or touch billing state) on a deck now linked to a different subscription --
        link switches only happen via the checkout reconciler or the admin."""
        self.set_deck(paid_until=None, stripe_subscription_id='sub_new')
        summary = self.tenant.sync_from_stripe_subscription(self.make_subscription(id='sub_old'))
        self.assertIn('ignored', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_new')
        self.assertIsNone(self.tenant.paid_until)

    def test_sync__cap_from_price_metadata_and_fallback_map(self):
        """max_active_users comes from the Price's metadata; the settings tier map
        is the fallback; with neither, the cap is left alone."""
        from django.test import override_settings as override

        self.set_deck(max_active_users=5)
        sub = self.make_subscription()
        sub['items']['data'][0]['price']['metadata'] = {'max_active_users': '40'}
        self.tenant.sync_from_stripe_subscription(sub)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.max_active_users, 40)

        with override(STRIPE_PRICE_TIER_MAP={'price_x': 80}):
            self.tenant.sync_from_stripe_subscription(self.make_subscription())
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.max_active_users, 80)

        self.tenant.sync_from_stripe_subscription(self.make_subscription())  # no metadata, no map
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.max_active_users, 80)  # untouched

    def test_sync__canceled_event_without_an_id_unlinks_nothing(self):
        """A malformed cancellation payload with no subscription id (which the
        identity guard cannot see) must not unlink the deck's current
        subscription: unlinking requires an exact id match."""
        self.set_deck(paid_until=self.PERIOD_END, stripe_subscription_id='sub_sync')
        summary = self.tenant.sync_from_stripe_subscription(
            self.make_subscription(id='', status='canceled'))
        self.assertEqual(summary, 'no changes')
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_sync')

    def test_sync__canceled_when_already_unlinked_is_a_no_op(self):
        """A cancellation event for a deck already unlinked changes nothing (a
        re-delivered deletion after the admin cleared the link, for example)."""
        self.set_deck(paid_until=self.PERIOD_END, stripe_subscription_id='')
        summary = self.tenant.sync_from_stripe_subscription(self.make_subscription(status='canceled'))
        self.assertEqual(summary, 'no changes')

    def test_sync__canceled_subscription_unlinks_but_keeps_paid_until(self):
        """A canceled subscription clears the sub id (it's gone) but keeps paid_until:
        the deck is paid through its period end; it just stops renewing."""
        self.set_deck(paid_until=self.PERIOD_END, stripe_subscription_id='sub_sync', stripe_customer_id='cus_sync')
        summary = self.tenant.sync_from_stripe_subscription(self.make_subscription(status='canceled'))
        self.assertIn('stripe_subscription_id=', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_subscription_id, '')
        self.assertEqual(self.tenant.stripe_customer_id, 'cus_sync')  # kept for the portal
        self.assertEqual(self.tenant.paid_until, self.PERIOD_END)


class StripeEventLogModelTest(ByteDeckTenantTestCase):
    """Tests for the StripeEventLog webhook idempotence/audit model (PR 7)."""

    def test_str__identifies_event_and_resolved_deck(self):
        """The string form names the event, its type, and the resolved deck (or not)."""
        from tenant.models import StripeEventLog

        log = StripeEventLog.objects.create(event_id='evt_1', event_type='invoice.paid', schema_name='test')
        self.assertEqual(str(log), 'evt_1 (invoice.paid) -> test')
        log = StripeEventLog.objects.create(event_id='evt_2', event_type='ping')
        self.assertEqual(str(log), 'evt_2 (ping) -> unresolved')


class SyncPaymentGatingTest(ByteDeckTenantTestCase):
    """Regression tests: sync must never grant access for unpaid subscription states
    (self-review of #1729 PR 7 -- the webhook path must gate like the checkout
    reconciler does)."""

    PERIOD_END_TS = 1800014400  # 2027-01-15 12:00 UTC

    def set_deck(self, **fields):
        """Persist billing fields on this deck's Tenant row and refresh the instance."""
        Tenant.objects.filter(pk=self.tenant.pk).update(**fields)
        self.tenant.refresh_from_db()

    def make_subscription(self, status):
        """A subscription double in the given status, with a period end and a tier cap."""
        return {
            'id': 'sub_gate', 'status': status, 'customer': 'cus_gate',
            'items': {'data': [{'current_period_end': self.PERIOD_END_TS,
                                'price': {'id': 'p', 'metadata': {'max_active_users': '40'}}}]},
        }

    def test_sync__incomplete_first_payment_grants_nothing(self):
        """An 'incomplete' subscription (failed 3DS at checkout) links the sub id for
        later reconciliation but grants no paid period and no tier cap."""
        self.set_deck(paid_until=None, max_active_users=5, stripe_subscription_id='')
        self.tenant.sync_from_stripe_subscription(self.make_subscription('incomplete'))
        self.tenant.refresh_from_db()
        self.assertIsNone(self.tenant.paid_until)
        self.assertEqual(self.tenant.max_active_users, 5)
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_gate')  # identifiable for later sync

    def test_sync__past_due_renewal_does_not_extend_access(self):
        """Stripe rolls current_period_end forward at renewal even while payment is
        failing (past_due); paid_until must NOT follow -- the grace period covers
        this window until invoice.paid actually lands."""
        original = date(2026, 9, 1)
        self.set_deck(paid_until=original, stripe_subscription_id='sub_gate')
        summary = self.tenant.sync_from_stripe_subscription(self.make_subscription('past_due'))
        self.assertEqual(summary, 'no changes')
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.paid_until, original)

    def test_sync__payment_recovery_extends_access(self):
        """Once the same subscription recovers to 'active' (invoice.paid), the held-back
        period end applies."""
        self.set_deck(paid_until=date(2026, 9, 1), stripe_subscription_id='sub_gate')
        self.tenant.sync_from_stripe_subscription(self.make_subscription('active'))
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.paid_until, date(2027, 1, 15))
        self.assertEqual(self.tenant.max_active_users, 40)


class TenantQuestCountTest(ByteDeckTenantTestCase):
    """Tests for the cached quest-count stat's AVAILABLE-quests semantics
    (maintainer request, 2026-08-09)."""

    def test_get_quest_count__counts_only_the_available_quest_pool(self):
        """get_quest_count() counts the pool the students' Available quests tab
        draws from (published, past its start date, not expired, active campaign
        or none), and excludes drafts, archived, expired, not-yet-started, and
        inactive-campaign quests, which the old un-archived count included."""
        from django.utils.timezone import localdate

        baseline = self.tenant.get_quest_count()  # the seeded test deck may ship quests

        baker.make('quest_manager.Quest', published=True)  # the one countable quest
        inactive_campaign = baker.make('quest_manager.Category', published=False)
        baker.make('quest_manager.Quest', published=True, campaign=inactive_campaign)
        baker.make('quest_manager.Quest', published=False)  # draft
        baker.make('quest_manager.Quest', published=True, archived=True)
        baker.make('quest_manager.Quest', published=True, date_expired=localdate() - timedelta(days=1))
        baker.make('quest_manager.Quest', published=True, date_available=localdate() + timedelta(days=1))

        self.assertEqual(self.tenant.get_quest_count(), baseline + 1)
