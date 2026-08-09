from datetime import date, datetime, timezone as dt_timezone
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from freezegun import freeze_time

from django.contrib.auth import get_user_model

from django_tenants.utils import schema_context

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from tenant.billing import (
    billing_configured, checkout_trial_end, create_checkout_session, reconcile_checkout_session,
    subscription_period_end_date,
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
            subscription_period_end_date({'current_period_end': self.PERIOD_END_TS}),
            date(2026, 9, 14),
        )

    def test_period_end__items_fallback(self):
        """Newer API shape: current_period_end lives on the subscription's items."""
        subscription = {'items': {'data': [{'current_period_end': self.PERIOD_END_TS}]}}
        self.assertEqual(subscription_period_end_date(subscription), date(2026, 9, 14))

    def test_period_end__missing_returns_none(self):
        """No period end in either shape (or no items at all) -> None."""
        self.assertIsNone(subscription_period_end_date({}))
        self.assertIsNone(subscription_period_end_date({'items': {'data': []}}))


@freeze_time("2026-08-15 20:00:00")  # midday Pacific so localtime dates are stable
class CheckoutTrialEndTest(SimpleTestCase):
    """Tests for the mid-trial checkout trial_end pass-through (maintainer
    decision, 2026-08-06): a mid-trial subscriber keeps their remaining free
    time, so checkout starts the subscription `trialing` until the deck's
    existing trial ends.

    Deliberately SimpleTestCase rather than TenantTestCase (the approved
    exception for pure in-memory model tests): every deck here is an unsaved
    Tenant exercising pure date logic, and SimpleTestCase makes that
    no-database invariant executable by refusing all queries. Database-backed
    checkout behavior is covered by CreateCheckoutSessionTrialEndTest below."""

    def deck(self, trial_end_date=None, paid_until=None):
        """Build an unsaved in-memory Tenant with explicit billing dates.

        Args:
            trial_end_date (date | None): Value for Tenant.trial_end_date.
                Defaults to None (a dateless deck), overriding the model
                field's default, which would give every bare deck a 60-day
                trial.
            paid_until (date | None): Value for Tenant.paid_until, or None.

        Returns:
            Tenant: An unsaved deck; tests never persist it.
        """
        return Tenant(name='trialend', trial_end_date=trial_end_date, paid_until=paid_until)

    def test_checkout_trial_end__runs_to_local_midnight_after_the_trials_last_day(self):
        """A mid-trial deck's Stripe trial runs through local midnight AFTER
        trial_end_date: the deck's own trial covers that whole day."""
        end = checkout_trial_end(self.deck(trial_end_date=date(2026, 9, 14)))
        self.assertEqual(end, timezone.make_aware(datetime(2026, 9, 15, 0, 0)))

    def test_checkout_trial_end__none_when_the_trial_clock_does_not_govern(self):
        """Decks whose governing clock isn't the trial (a later paid date, or no
        dates at all) have no trial to preserve, so checkout bills immediately."""
        self.assertIsNone(
            checkout_trial_end(self.deck(trial_end_date=date(2026, 9, 14), paid_until=date(2026, 12, 1))))
        self.assertIsNone(checkout_trial_end(self.deck()))  # managed manually

    def test_checkout_trial_end__governing_clock_decides_with_both_dates(self):
        """With BOTH dates set the governing (latest) clock decides (#1734 B4):
        a trial outlasting an old paid date passes its end through, equal dates
        speak subscription language (no pass-through), and a later paid date
        bills immediately."""
        self.assertEqual(
            checkout_trial_end(self.deck(trial_end_date=date(2026, 9, 14), paid_until=date(2026, 8, 1))),
            timezone.make_aware(datetime(2026, 9, 15, 0, 0)))
        self.assertIsNone(
            checkout_trial_end(self.deck(trial_end_date=date(2026, 9, 14), paid_until=date(2026, 9, 14))))
        self.assertIsNone(
            checkout_trial_end(self.deck(trial_end_date=date(2026, 9, 14), paid_until=date(2026, 12, 1))))

    def test_checkout_trial_end__none_when_the_trial_ends_too_soon(self):
        """Stripe requires trial_end at least 48 hours out, so a trial-governed
        deck whose trial is nearly over (or already lapsed into grace) gets a
        plain bill-now checkout instead of a doomed API call."""
        self.assertIsNone(checkout_trial_end(self.deck(trial_end_date=date(2026, 8, 10))))  # lapsed into grace
        self.assertIsNone(checkout_trial_end(self.deck(trial_end_date=date(2026, 8, 15))))  # ends today
        self.assertIsNone(checkout_trial_end(self.deck(trial_end_date=date(2026, 8, 16))))  # under the 49h floor
        self.assertIsNotNone(checkout_trial_end(self.deck(trial_end_date=date(2026, 8, 17))))  # clears it
        # the floor is a strict cutoff: a trial ending EXACTLY 49h out is preserved, one
        # second later it isn't (midnight after Aug 17 local = 2026-08-18 07:00 UTC; -49h)
        with freeze_time("2026-08-16 06:00:00"):
            self.assertIsNotNone(checkout_trial_end(self.deck(trial_end_date=date(2026, 8, 17))))
        with freeze_time("2026-08-16 06:00:01"):
            self.assertIsNone(checkout_trial_end(self.deck(trial_end_date=date(2026, 8, 17))))


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
        deck's remaining free time as a unix timestamp) beside the schema
        stamping, and repeats that timestamp in the idempotency key: the
        parameters differ from a bill-now session, and from a session built for
        a different trial end, so neither retry shape can collide with a stale
        key."""
        Tenant.objects.filter(pk=self.tenant.pk).update(trial_end_date=date(2026, 9, 14), paid_until=None)
        self.tenant.refresh_from_db()
        kwargs = self.create_session()
        expected = int(timezone.make_aware(datetime(2026, 9, 15, 0, 0)).timestamp())
        self.assertEqual(
            kwargs['subscription_data'],
            {'metadata': {'schema_name': self.tenant.schema_name}, 'trial_end': expected})
        self.assertTrue(kwargs['idempotency_key'].endswith(f'-trial-{expected}'))

    def test_create_checkout_session__no_trial_end_when_not_applicable(self):
        """A deck with no trial time to keep (here: trial lapsed) gets a
        bill-now checkout: the subscription is still schema-stamped but carries
        no trial_end, and the idempotency key is unmarked."""
        Tenant.objects.filter(pk=self.tenant.pk).update(trial_end_date=date(2026, 8, 10), paid_until=None)
        self.tenant.refresh_from_db()
        kwargs = self.create_session()
        self.assertEqual(kwargs['subscription_data'], {'metadata': {'schema_name': self.tenant.schema_name}})
        # the full base key, not a substring check: a schema name containing "trial"
        # must not fail the unmarked-key assertion
        self.assertEqual(
            kwargs['idempotency_key'],
            f'deck-checkout-{self.tenant.schema_name}-{timezone.localdate()}')


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


class SubscriptionMaxActiveUsersTest(SimpleTestCase):
    """Tests for reading the tier cap off a Stripe subscription (epic #1729 PR 7)."""

    def make_subscription(self, metadata=None, price_id='price_x'):
        """A subscription double whose Price carries the given metadata."""
        return {'items': {'data': [{'price': {'id': price_id, 'metadata': metadata or {}}}]}}

    def test_cap__from_price_metadata(self):
        """metadata.max_active_users on the Price wins (dashboard-editable tiers)."""
        from tenant.billing import subscription_max_active_users

        self.assertEqual(subscription_max_active_users(self.make_subscription({'max_active_users': '40'})), 40)

    @override_settings(STRIPE_PRICE_TIER_MAP={'price_x': 80})
    def test_cap__falls_back_to_settings_tier_map(self):
        """Without Price metadata, the settings tier map resolves the cap by price id."""
        from tenant.billing import subscription_max_active_users

        self.assertEqual(subscription_max_active_users(self.make_subscription()), 80)

    def test_cap__none_when_unknown_or_malformed(self):
        """No metadata + no map entry -> None (leave the deck's cap alone); a
        malformed value is treated the same rather than crashing the sync."""
        from tenant.billing import subscription_max_active_users

        self.assertIsNone(subscription_max_active_users(self.make_subscription()))
        self.assertIsNone(subscription_max_active_users({'items': {'data': []}}))
        self.assertIsNone(subscription_max_active_users(self.make_subscription({'max_active_users': 'lots'})))

    def test_cap__rejects_values_below_the_unlimited_sentinel(self):
        """-1 means unlimited (the Tenant field convention) and passes through, but
        anything below it (e.g. -2) would read as a cap every count exceeds, so it
        resolves to None and the sync leaves the deck's cap alone."""
        from tenant.billing import subscription_max_active_users

        self.assertEqual(subscription_max_active_users(self.make_subscription({'max_active_users': '-1'})), -1)
        self.assertIsNone(subscription_max_active_users(self.make_subscription({'max_active_users': '-2'})))


@override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
class HandleWebhookEventTest(ByteDeckTenantTestCase):
    """Tests for the webhook event dispatcher (epic #1729 PR 7, plan §5.2).

    Events are plain dict doubles; anything that would call Stripe's API
    (subscription retrieval) is mocked at the tenant.billing.stripe seam.
    """

    PERIOD_END_TS = 1800014400  # 2027-01-15 12:00 UTC -> 2027-01-15 local
    PERIOD_END = date(2027, 1, 15)

    def set_deck(self, **fields):
        """Persist billing fields on this deck's Tenant row and refresh the instance."""
        Tenant.objects.filter(pk=self.tenant.pk).update(**fields)
        self.tenant.refresh_from_db()

    def make_event(self, event_type, obj):
        """A Stripe Event double."""
        return {'id': 'evt_x', 'type': event_type, 'data': {'object': obj}}

    def stripe_subscription(self, **overrides):
        """A subscription API-retrieval double."""
        subscription = {
            'id': 'sub_wh', 'status': 'active', 'customer': 'cus_wh',
            'items': {'data': [{'current_period_end': self.PERIOD_END_TS, 'price': {'id': 'price_x', 'metadata': {}}}]},
        }
        subscription.update(overrides)
        return subscription

    def test_checkout_completed__links_customer_and_syncs_subscription(self):
        """checkout.session.completed resolves the deck by its schema binding, links
        the customer, and syncs the subscription (retrieved from Stripe)."""
        from tenant.billing import handle_webhook_event

        self.set_deck(paid_until=None, stripe_customer_id='', stripe_subscription_id='')
        event = self.make_event('checkout.session.completed', {
            'client_reference_id': self.tenant.schema_name, 'customer': 'cus_wh', 'subscription': 'sub_wh',
        })
        with patch('tenant.billing.stripe.Subscription.retrieve', return_value=self.stripe_subscription()):
            schema_name, summary = handle_webhook_event(event)
        self.assertEqual(schema_name, self.tenant.schema_name)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, 'cus_wh')
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_wh')
        self.assertEqual(self.tenant.paid_until, self.PERIOD_END)

    def test_subscription_events__sync_through_the_single_write_path(self):
        """customer.subscription.* events resolve the deck (metadata stamped by our
        checkout, or stored ids) and sync directly from the event payload."""
        from tenant.billing import handle_webhook_event

        self.set_deck(paid_until=None, stripe_subscription_id='sub_wh')
        event = self.make_event('customer.subscription.updated', self.stripe_subscription())
        schema_name, summary = handle_webhook_event(event)
        self.assertEqual(schema_name, self.tenant.schema_name)
        self.assertIn('paid_until', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.paid_until, self.PERIOD_END)

        # metadata-based resolution works even when nothing is linked yet
        self.set_deck(paid_until=None, stripe_subscription_id='', stripe_customer_id='')
        event = self.make_event(
            'customer.subscription.created',
            self.stripe_subscription(metadata={'schema_name': self.tenant.schema_name}),
        )
        schema_name, summary = handle_webhook_event(event)
        self.assertEqual(schema_name, self.tenant.schema_name)  # resolved via the stamped metadata
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_wh')

    def test_invoice_paid__retrieves_subscription_and_syncs(self):
        """invoice.paid resolves the deck by its stored ids and re-syncs from a fresh
        subscription retrieval (the invoice payload doesn't carry the period end)."""
        from tenant.billing import handle_webhook_event

        self.set_deck(paid_until=None, stripe_customer_id='cus_wh', stripe_subscription_id='sub_wh')
        event = self.make_event('invoice.paid', {'id': 'in_1', 'customer': 'cus_wh', 'subscription': 'sub_wh'})
        with patch('tenant.billing.stripe.Subscription.retrieve', return_value=self.stripe_subscription()):
            _, summary = handle_webhook_event(event)
        self.assertIn('paid_until', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.paid_until, self.PERIOD_END)

    @override_settings(DECK_NOTICES_ENABLED=True)
    def test_invoice_payment_failed__delivers_owner_notice_once_per_invoice(self):
        """invoice.payment_failed sends the owner a heads-up through the notices
        machinery, exactly once per failing invoice (Stripe retries re-deliver)."""
        from allauth.account.models import EmailAddress
        from django.core import mail
        from siteconfig.models import SiteConfig

        from tenant.billing import handle_webhook_event
        from tenant.models import DeckNotice

        # give the owner an email and a distinct AI sender, as the delivery tests do
        with schema_context(self.tenant.schema_name):
            config = SiteConfig.get()
            owner = config.deck_owner
            if not owner.email:
                email_address = EmailAddress.objects.add_email(request=None, user=owner, email='owner@example.com')
                email_address.set_as_primary()
                email_address.save()
            if config.deck_ai == config.deck_owner:
                config.deck_ai = get_user_model().objects.create(username='deck_ai_bot2', is_staff=True)
                config.save()

        self.set_deck(stripe_customer_id='cus_wh', stripe_subscription_id='sub_wh')
        event = self.make_event('invoice.payment_failed', {'id': 'in_fail', 'customer': 'cus_wh', 'subscription': 'sub_wh'})

        from unittest.mock import patch as mock_patch

        from tenant import tasks
        with mock_patch.object(
            tasks.send_email_message, 'apply_async',
            side_effect=lambda kwargs=None, queue=None: tasks.send_email_message.apply(kwargs=kwargs),
        ):
            _, summary = handle_webhook_event(event)
            self.assertIn('sent payment-failure notice', summary)
            _, summary = handle_webhook_event(event)  # Stripe retry of the same invoice
            self.assertIn('already sent', summary)

        self.assertEqual(DeckNotice.objects.filter(kind=DeckNotice.KIND_PAYMENT_FAILED).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('failed-payment warning', mail.outbox[0].subject)
        html = mail.outbox[0].alternatives[0][0]
        self.assertIn('non-profit Society', html)  # the shared footer rides along
        self.assertNotIn('&mdash;', html)  # no em dashes in subscription emails (#2208)

    def test_invoice_payment_failed__report_only_when_notices_disabled(self):
        """With DECK_NOTICES_ENABLED off (the default), the payment-failure notice is
        logged but nothing is recorded or sent -- same rollout gate as the engine."""
        from django.core import mail

        from tenant.billing import handle_webhook_event
        from tenant.models import DeckNotice

        self.set_deck(stripe_customer_id='cus_wh')
        event = self.make_event('invoice.payment_failed', {'id': 'in_fail', 'customer': 'cus_wh'})
        _, summary = handle_webhook_event(event)
        self.assertIn('REPORT-ONLY', summary)
        self.assertFalse(DeckNotice.objects.filter(kind=DeckNotice.KIND_PAYMENT_FAILED).exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_handle_webhook_event__unresolved_and_ignored(self):
        """Events that resolve to no deck, and unhandled event types, are acknowledged
        with a log summary and change nothing."""
        from tenant.billing import handle_webhook_event

        _, summary = handle_webhook_event(self.make_event('invoice.paid', {'customer': 'cus_nobody'}))
        self.assertEqual(summary, 'no deck resolved')
        _, summary = handle_webhook_event(self.make_event('charge.refunded', {}))
        self.assertIn('ignored event type', summary)

    def test_invoice_paid__without_subscription_is_ignored(self):
        """A one-off (non-subscription) invoice resolves the deck but syncs nothing."""
        from tenant.billing import handle_webhook_event

        self.set_deck(stripe_customer_id='cus_wh')
        _, summary = handle_webhook_event(self.make_event('invoice.paid', {'id': 'in_2', 'customer': 'cus_wh'}))
        self.assertIn('invoice without subscription', summary)

    def test_invoice_paid__newer_api_shape_resolves_subscription_from_parent(self):
        """Newer Stripe API versions carry the invoice's subscription under
        parent.subscription_details; the handler reads both shapes."""
        from tenant.billing import handle_webhook_event

        self.set_deck(paid_until=None, stripe_customer_id='cus_wh', stripe_subscription_id='sub_wh')
        event = self.make_event('invoice.paid', {
            'id': 'in_3', 'customer': 'cus_wh',
            'parent': {'subscription_details': {'subscription': 'sub_wh'}},
        })
        with patch('tenant.billing.stripe.Subscription.retrieve', return_value=self.stripe_subscription()):
            _, summary = handle_webhook_event(event)
        self.assertIn('paid_until', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.paid_until, self.PERIOD_END)

    def test_checkout_completed__session_without_customer_clears_nothing(self):
        """A checkout.session.completed lacking a customer must not CLEAR a stored
        customer link (the update is guarded on a truthy value)."""
        from tenant.billing import handle_webhook_event

        self.set_deck(stripe_customer_id='cus_keep', stripe_subscription_id='')
        event = self.make_event('checkout.session.completed', {
            'client_reference_id': self.tenant.schema_name,
        })
        _, summary = handle_webhook_event(event)
        self.assertIn('no customer on session', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, 'cus_keep')

    def test_checkout_completed__stale_session_cannot_overwrite_newer_links(self):
        """A checkout.session.completed delivered late, for a checkout superseded by
        a newer one (the deck is already linked to a different customer and
        subscription), changes nothing: the sync's identity guard ignores the old
        subscription, and the customer link only follows the linked subscription."""
        from tenant.billing import handle_webhook_event

        self.set_deck(stripe_customer_id='cus_new', stripe_subscription_id='sub_new')
        event = self.make_event('checkout.session.completed', {
            'client_reference_id': self.tenant.schema_name, 'customer': 'cus_old', 'subscription': 'sub_old',
        })
        with patch('tenant.billing.stripe.Subscription.retrieve',
                   return_value=self.stripe_subscription(id='sub_old', customer='cus_old')):
            _, summary = handle_webhook_event(event)
        self.assertIn("not this deck's linked subscription", summary)
        self.assertIn('customer link kept', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, 'cus_new')
        self.assertEqual(self.tenant.stripe_subscription_id, 'sub_new')

    def test_checkout_completed__links_unlinked_deck_even_without_a_secret_key(self):
        """A server holding only the webhook secret cannot retrieve the session's
        subscription, but a fully unlinked deck still gets its customer linked:
        the follow-up customer.subscription.* events (which self-identify via
        their stamped metadata) complete the link from their own payloads."""
        from django.test import override_settings as override

        from tenant.billing import handle_webhook_event

        self.set_deck(stripe_customer_id='', stripe_subscription_id='')
        event = self.make_event('checkout.session.completed', {
            'client_reference_id': self.tenant.schema_name, 'customer': 'cus_wh', 'subscription': 'sub_wh',
        })
        with override(STRIPE_SECRET_KEY=None):
            _, summary = handle_webhook_event(event)
        self.assertIn('retrieve skipped', summary)
        self.assertIn('linked customer', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, 'cus_wh')
        self.assertEqual(self.tenant.stripe_subscription_id, '')

    def test_sync_helper__skips_retrieve_without_a_secret_key(self):
        """A server holding only the webhook secret cannot retrieve subscriptions;
        the helper reports and skips instead of raising into a 500 that Stripe
        would retry for days."""
        from django.test import override_settings as override

        from tenant.billing import _sync_deck_from_subscription_id

        with override(STRIPE_SECRET_KEY=None):
            summary = _sync_deck_from_subscription_id(self.tenant, 'sub_wh')
        self.assertIn('retrieve skipped', summary)


@override_settings(STRIPE_SECRET_KEY='sk_test_123', STRIPE_PRICE_ID='price_123')
class ResolveDeckTest(ByteDeckTenantTestCase):
    """Tests for the webhook deck resolver's fallback chain (plan §5.2)."""

    def test_resolve__falls_through_schema_then_subscription_then_customer(self):
        """An unknown schema binding falls back to the stored subscription id, then
        the customer id; with nothing to go on it resolves to None."""
        from tenant.billing import _resolve_deck
        from tenant.models import Tenant

        Tenant.objects.filter(pk=self.tenant.pk).update(
            stripe_customer_id='cus_r', stripe_subscription_id='sub_r')

        deck = _resolve_deck(schema_name='no_such_schema', subscription_id='sub_r')
        self.assertEqual(deck.pk, self.tenant.pk)
        deck = _resolve_deck(subscription_id='sub_gone', customer_id='cus_r')
        self.assertEqual(deck.pk, self.tenant.pk)
        self.assertIsNone(_resolve_deck())

    def test_handlers__acknowledge_unresolvable_events(self):
        """Each handler type acknowledges an event it can't map to a deck, and a
        checkout-completed without a subscription only links the customer."""
        from tenant.billing import handle_webhook_event
        from tenant.models import Tenant

        for event_type, obj in (
            ('checkout.session.completed', {'client_reference_id': 'no_such_schema'}),
            ('customer.subscription.updated', {'id': 'sub_gone', 'customer': 'cus_gone'}),
            ('invoice.payment_failed', {'id': 'in_x', 'customer': 'cus_gone'}),
        ):
            schema_name, summary = handle_webhook_event({'id': 'evt_r', 'type': event_type, 'data': {'object': obj}})
            self.assertEqual((schema_name, summary), ('', 'no deck resolved'), event_type)

        # setup-mode checkout (no subscription on the session): customer link only
        Tenant.objects.filter(pk=self.tenant.pk).update(stripe_customer_id='', stripe_subscription_id='')
        _, summary = handle_webhook_event({'id': 'evt_r2', 'type': 'checkout.session.completed',
                                           'data': {'object': {'client_reference_id': self.tenant.schema_name,
                                                               'customer': 'cus_only'}}})
        self.assertIn('linked customer', summary)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_customer_id, 'cus_only')
        self.assertEqual(self.tenant.stripe_subscription_id, '')
