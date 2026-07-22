from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from freezegun import freeze_time

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from tenant.billing import _subscription_period_end_date, billing_configured, reconcile_checkout_session
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

        session = {'status': 'complete', 'customer': 'cus_9', 'subscription': {'id': 'sub_9'}}
        with patch('tenant.billing.stripe.checkout.Session.retrieve', return_value=session):
            self.assertTrue(reconcile_checkout_session(self.tenant, 'cs_9'))

        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, 'cus_9')
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_9')
        self.assertEqual(self.tenant.paid_until, original_paid_until)
