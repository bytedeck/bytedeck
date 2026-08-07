from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from freezegun import freeze_time

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from tenant.billing import (
    _subscription_period_end_date, billing_configured, checkout_trial_end, create_checkout_session,
    reconcile_checkout_session,
)
from tenant.models import Tenant


class BillingConfiguredTest(SimpleTestCase):
    """Tests for the Stripe configuration presence check (epic #1729 PR 6)."""

    @override_settings(STRIPE_SECRET_KEY=None, STRIPE_PRICE_ID=None)
    def test_billing_configured__false_without_keys(self):
        """Billing is off when the secret key and price are absent (the dev default)."""
        self.assertFalse(billing_configured())

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID=None)
    def test_billing_configured__false_without_price(self):
        """A secret key alone isn't enough -- checkout needs the subscription Price too."""
        self.assertFalse(billing_configured())

    @override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
    def test_billing_configured__true_with_key_and_price(self):
        """Both present: checkout can run."""
        self.assertTrue(billing_configured())


@freeze_time("2026-08-15 20:00:00")  # midday Pacific so localtime dates are stable
class SubscriptionPeriodEndDateTest(SimpleTestCase):
    """Tests for reading current_period_end across Stripe API shapes (epic #1729 PR 6)."""

    # 2026-09-14 12:00 UTC -> 2026-09-14 in America/Vancouver
    PERIOD_END_TS = int(datetime(2026, 9, 14, 12, 0, tzinfo=dt_timezone.utc).timestamp())

    def test_period_end__top_level_field(self):
        """Older API shape: current_period_end directly on the subscription."""
        self.assertEqual(
            _subscription_period_end_date({'current_period_end': self.PERIOD_END_TS}),
            date(2026, 9, 14),
        )

    def test_period_end__items_fallback(self):
        """Newer API shape: current_period_end lives on the subscription's items."""
        subscription = {'items': {'data': [{'current_period_end': self.PERIOD_END_TS}]}}
        self.assertEqual(_subscription_period_end_date(subscription), date(2026, 9, 14))

    def test_period_end__missing_returns_none(self):
        """No period end in either shape (or no items at all) -> None."""
        self.assertIsNone(_subscription_period_end_date({}))
        self.assertIsNone(_subscription_period_end_date({'items': {'data': []}}))


@freeze_time("2026-08-15 20:00:00")  # midday Pacific so localtime dates are stable
class CheckoutTrialEndTest(SimpleTestCase):
    """Tests for the mid-trial checkout trial_end pass-through (maintainer
    decision, 2026-08-06): a mid-trial subscriber keeps their remaining free
    time, so checkout starts the subscription `trialing` until the deck's
    existing trial ends. Pure date logic on unsaved in-memory decks."""

    def deck(self, trial_end_date=None, paid_until=None):
        """Build an unsaved Tenant with explicit billing dates (overriding the
        field default, which would give every bare deck a 60-day trial)."""
        return Tenant(name='trialend', trial_end_date=trial_end_date, paid_until=paid_until)

    def test_checkout_trial_end__runs_to_local_midnight_after_the_trials_last_day(self):
        """A mid-trial deck's Stripe trial runs through local midnight AFTER
        trial_end_date: the deck's own trial covers that whole day."""
        end = checkout_trial_end(self.deck(trial_end_date=date(2026, 9, 14)))
        self.assertEqual(end, timezone.make_aware(datetime(2026, 9, 15, 0, 0)))

    def test_checkout_trial_end__none_when_not_on_trial(self):
        """Paid, lapsed-trial, and dateless decks have no trial time to keep,
        so checkout bills immediately as usual."""
        self.assertIsNone(
            checkout_trial_end(self.deck(trial_end_date=date(2026, 9, 14), paid_until=date(2026, 12, 1))))
        self.assertIsNone(checkout_trial_end(self.deck(trial_end_date=date(2026, 8, 10))))  # trial lapsed
        self.assertIsNone(checkout_trial_end(self.deck()))  # managed manually

    def test_checkout_trial_end__none_when_the_trial_ends_too_soon(self):
        """Stripe requires trial_end at least 48 hours out, so a nearly-over
        trial gets a plain bill-now checkout instead of a doomed API call."""
        self.assertIsNone(checkout_trial_end(self.deck(trial_end_date=date(2026, 8, 15))))  # ends today
        self.assertIsNone(checkout_trial_end(self.deck(trial_end_date=date(2026, 8, 16))))  # under the 49h floor
        self.assertIsNotNone(checkout_trial_end(self.deck(trial_end_date=date(2026, 8, 17))))  # clears it


@override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
@freeze_time("2026-08-15 20:00:00")  # midday Pacific so localtime dates are stable
class CreateCheckoutSessionTrialEndTest(ByteDeckTenantTestCase):
    """create_checkout_session forwards the mid-trial trial_end to Stripe (with
    a trial-marked idempotency key) exactly when checkout_trial_end applies."""

    def create_session(self):
        """Run create_checkout_session with Stripe mocked; return the call kwargs."""
        with patch('tenant.billing.stripe.checkout.Session.create') as mock_create:
            mock_create.return_value.url = 'https://stripe.example/session'
            self.assertEqual(create_checkout_session(self.tenant), 'https://stripe.example/session')
        return mock_create.call_args.kwargs

    def test_create_checkout_session__mid_trial_passes_trial_end(self):
        """A mid-trial deck's checkout carries subscription_data.trial_end (the
        deck's remaining free time as a unix timestamp) and marks the
        idempotency key, since the parameters differ from a bill-now session."""
        Tenant.objects.filter(pk=self.tenant.pk).update(trial_end_date=date(2026, 9, 14), paid_until=None)
        self.tenant.refresh_from_db()
        kwargs = self.create_session()
        expected = int(timezone.make_aware(datetime(2026, 9, 15, 0, 0)).timestamp())
        self.assertEqual(kwargs['subscription_data'], {'trial_end': expected})
        self.assertTrue(kwargs['idempotency_key'].endswith('-trial'))

    def test_create_checkout_session__no_trial_end_when_not_applicable(self):
        """A deck with no trial time to keep (here: trial lapsed) gets a plain
        bill-now checkout: no subscription_data, unmarked idempotency key."""
        Tenant.objects.filter(pk=self.tenant.pk).update(trial_end_date=date(2026, 8, 10), paid_until=None)
        self.tenant.refresh_from_db()
        kwargs = self.create_session()
        self.assertNotIn('subscription_data', kwargs)
        self.assertFalse(kwargs['idempotency_key'].endswith('-trial'))


@override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
class ReconcileCheckoutSessionTest(ByteDeckTenantTestCase):
    """Tests for post-checkout reconciliation edge cases (epic #1729 PR 6).

    The happy path and error handling are covered end-to-end through the status
    endpoint in test_views; these pin the module-level edges.
    """

    def test_reconcile__missing_period_end_links_ids_but_keeps_paid_until(self):
        """A completed session whose subscription carries no period end still links
        the deck to Stripe, but leaves paid_until alone rather than clearing it."""
        original_paid_until = date(2027, 1, 1)
        Tenant.objects.filter(schema_name=self.tenant.schema_name).update(
            paid_until=original_paid_until, stripe_customer_id='', stripe_subscription_id='')

        session = {
            'status': 'complete', 'client_reference_id': self.tenant.schema_name,
            'customer': 'cus_9', 'subscription': {'id': 'sub_9', 'status': 'active'},
        }
        with patch('tenant.billing.stripe.checkout.Session.retrieve', return_value=session):
            self.assertTrue(reconcile_checkout_session(self.tenant, 'cs_9'))

        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, 'cus_9')
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_9')
        self.assertEqual(self.tenant.paid_until, original_paid_until)
