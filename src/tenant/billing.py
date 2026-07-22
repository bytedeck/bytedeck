"""Stripe glue for deck subscriptions (epic #1729 PR 6).

All Stripe API access for the subscription page lives here so the views stay
thin and tests can mock a single seam (``tenant.billing.stripe``). Nothing in
this module is reachable when billing isn't configured: the page checks
:func:`billing_configured` first and falls back to the public subscribe page.

Two flows feed deck billing state, both defined here:

* Checkout (PR 6): after Checkout redirects back, the "activating" page polls a
  status endpoint that calls :func:`reconcile_checkout_session` -- the
  never-assume-the-webhook-landed path (plan §5.4).
* Webhooks (PR 7): Stripe posts events to the public-schema endpoint, which
  verifies the signature and dispatches to :func:`handle_webhook_event`. Every
  handler is a thin translator that resolves the deck and funnels through
  ``Tenant.sync_from_stripe_subscription`` -- the single billing write path.
"""
from datetime import datetime, timezone as dt_timezone

import stripe

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localdate


def billing_configured():
    """Whether Stripe checkout can run: the secret key and the subscription Price are set.

    The publishable key isn't required by the redirect-based Checkout flow, and the
    webhook secret only matters to the webhook endpoint (PR 7).
    """
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID)


def _subscription_page_url(deck):
    """Absolute URL of this deck's subscription page (Stripe needs absolute URLs)."""
    return deck.get_root_url() + reverse('decks:subscription')


def create_checkout_session(deck):
    """Create a subscription Checkout Session for an unlinked deck; return its URL.

    The deck is identified to Stripe three ways (client_reference_id, metadata,
    and the customer email), so the webhook (PR 7) and manual reconciliation can
    always find their way back to the schema. The idempotency key means a
    double-click or same-day retry with identical parameters reuses the same
    session instead of minting duplicates.

    Args:
        deck (Tenant): The current deck; must not already have a stripe_customer_id.

    Returns:
        str: The Stripe-hosted checkout URL to redirect the owner to.
    """
    session = stripe.checkout.Session.create(
        api_key=settings.STRIPE_SECRET_KEY,
        mode='subscription',
        line_items=[{'price': settings.STRIPE_PRICE_ID, 'quantity': 1}],
        client_reference_id=deck.schema_name,
        customer_email=deck.get_owner_email_cached() or None,
        metadata={'schema_name': deck.schema_name},
        # stamp the subscription too, so webhook subscription events (PR 7)
        # self-identify without a lookup
        subscription_data={'metadata': {'schema_name': deck.schema_name}},
        # Checkout substitutes the real session id into the literal placeholder
        success_url=deck.get_root_url() + reverse('decks:subscription_activating') + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=_subscription_page_url(deck),
        idempotency_key=f'deck-checkout-{deck.schema_name}-{localdate()}',
    )
    return session.url


def create_portal_session(deck):
    """Create a Billing Portal session for a Stripe-linked deck; return its URL.

    The portal is where a linked deck renews, upgrades, changes card, or cancels
    -- Stripe hosts all of it; we only need the customer id.

    Args:
        deck (Tenant): The current deck; must have a stripe_customer_id.

    Returns:
        str: The Stripe-hosted portal URL to redirect the owner to.
    """
    session = stripe.billing_portal.Session.create(
        api_key=settings.STRIPE_SECRET_KEY,
        customer=deck.stripe_customer_id,
        return_url=_subscription_page_url(deck),
    )
    return session.url


def subscription_period_end_date(subscription):
    """The subscription's current period end as a local date, or None.

    Newer Stripe API versions moved ``current_period_end`` from the subscription
    onto its items; accept either shape (tests pin both).
    """
    period_end = subscription.get('current_period_end')
    if period_end is None:
        items = subscription.get('items') or {}
        data = items.get('data') or []
        if data:
            period_end = data[0].get('current_period_end')
    if period_end is None:
        return None
    return timezone.localtime(datetime.fromtimestamp(period_end, tz=dt_timezone.utc)).date()


def reconcile_checkout_session(deck, session_id):
    """Link the deck to its just-completed Checkout Session, if it completed.

    Retrieves the session (with its subscription expanded) and, when payment went
    through, records the customer/subscription ids on the Tenant row and advances
    ``paid_until`` to the subscription's current period end. Safe to call
    repeatedly -- reconciling an already-linked deck is a no-op update with the
    same values.

    Args:
        deck (Tenant): The current deck.
        session_id (str): The Checkout Session id from the success-URL query string.

    Returns:
        bool: True when the deck is linked and paid up as a result (or already was).
    """
    from tenant.models import Tenant
    from tenant.utils import invalidate_current_deck_cache

    session = stripe.checkout.Session.retrieve(
        session_id, api_key=settings.STRIPE_SECRET_KEY, expand=['subscription'],
    )
    # The session id arrives via the success-URL query string, so never trust it
    # blindly: the session must be one THIS deck's checkout created (bound via
    # client_reference_id/metadata), or a session id from some other deck's
    # checkout could write foreign Stripe ids onto this tenant.
    metadata = session.get('metadata') or {}
    if deck.schema_name not in (session.get('client_reference_id'), metadata.get('schema_name')):
        return False
    if session.get('status') != 'complete' or not session.get('subscription'):
        return False

    # A complete session only means checkout finished -- the subscription can
    # still be 'incomplete' (e.g. failed 3DS). Only active/trialing gets access.
    subscription = session['subscription']
    if subscription.get('status') not in ('active', 'trialing'):
        return False
    updates = {
        'stripe_customer_id': session.get('customer') or '',
        'stripe_subscription_id': subscription.get('id') or '',
    }
    paid_until = subscription_period_end_date(subscription)
    if paid_until is not None:
        updates['paid_until'] = paid_until
    Tenant.objects.filter(schema_name=deck.schema_name).update(**updates)
    invalidate_current_deck_cache(deck.schema_name)  # the banner should update immediately
    return True


def subscription_max_active_users(subscription):
    """The current-student cap this subscription's Price grants, or None.

    Tier configuration lives on the Stripe Price as ``metadata.max_active_users``
    (dashboard-editable, plan §2), with ``settings.STRIPE_PRICE_TIER_MAP``
    (price_id -> cap) as the fallback for Prices whose metadata was never set.
    Returns None -- leave the deck's cap alone -- when neither source knows.
    """
    items = subscription.get('items') or {}
    data = items.get('data') or []
    price = (data[0].get('price') or {}) if data else {}
    metadata = price.get('metadata') or {}
    raw = metadata.get('max_active_users')
    if raw is None:
        raw = (settings.STRIPE_PRICE_TIER_MAP or {}).get(price.get('id'))
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _resolve_deck(schema_name=None, customer_id=None, subscription_id=None):
    """Find the Tenant a webhook event belongs to, or None.

    Resolution order (plan §5.2): explicit schema binding (client_reference_id /
    metadata, stamped by our checkout) first, then the stored Stripe ids.
    """
    from tenant.models import Tenant

    if schema_name:
        deck = Tenant.objects.filter(schema_name=schema_name).first()
        if deck is not None:
            return deck
    if subscription_id:
        deck = Tenant.objects.filter(stripe_subscription_id=subscription_id).first()
        if deck is not None:
            return deck
    if customer_id:
        return Tenant.objects.filter(stripe_customer_id=customer_id).first()
    return None


def _sync_deck_from_subscription_id(deck, subscription_id):
    """Retrieve a subscription from Stripe and run the single-write-path sync."""
    subscription = stripe.Subscription.retrieve(subscription_id, api_key=settings.STRIPE_SECRET_KEY)
    return deck.sync_from_stripe_subscription(subscription)


def handle_webhook_event(event):
    """Dispatch one verified Stripe webhook event; return a log summary string.

    Handlers are thin translators (plan §5.2): resolve the deck, then call one
    named method -- ``Tenant.sync_from_stripe_subscription`` for anything that
    changes billing state, the notices machinery for payment failures. Unhandled
    event types are logged and acknowledged. Idempotence (duplicate delivery)
    is enforced by the caller via StripeEventLog before this runs.
    """
    from django_tenants.utils import tenant_context

    event_type = event.get('type', '')
    obj = (event.get('data') or {}).get('object') or {}
    metadata = obj.get('metadata') or {}

    if event_type == 'checkout.session.completed':
        deck = _resolve_deck(schema_name=obj.get('client_reference_id') or metadata.get('schema_name'),
                             customer_id=obj.get('customer'))
        if deck is None:
            return 'no deck resolved'
        # link the customer now; the subscription sync follows via retrieve
        # (the webhook payload carries the subscription only as an id string)
        from tenant.models import Tenant
        Tenant.objects.filter(pk=deck.pk).update(stripe_customer_id=obj.get('customer') or '')
        summary = 'linked customer'
        if obj.get('subscription'):
            summary += '; ' + _sync_deck_from_subscription_id(deck, obj['subscription'])
        return f'{deck.schema_name}: {summary}'

    if event_type in ('customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted'):
        deck = _resolve_deck(schema_name=metadata.get('schema_name'),
                             customer_id=obj.get('customer'), subscription_id=obj.get('id'))
        if deck is None:
            return 'no deck resolved'
        return f'{deck.schema_name}: {deck.sync_from_stripe_subscription(obj)}'

    if event_type == 'invoice.paid':
        subscription_id = obj.get('subscription')
        deck = _resolve_deck(customer_id=obj.get('customer'), subscription_id=subscription_id)
        if deck is None:
            return 'no deck resolved'
        if not subscription_id:
            return f'{deck.schema_name}: invoice without subscription, ignored'
        return f'{deck.schema_name}: {_sync_deck_from_subscription_id(deck, subscription_id)}'

    if event_type == 'invoice.payment_failed':
        deck = _resolve_deck(customer_id=obj.get('customer'), subscription_id=obj.get('subscription'))
        if deck is None:
            return 'no deck resolved'
        # Delivery resolves the owner/staff from the deck's schema, and respects
        # the same report-only rollout gate as the reminder engine.
        from tenant.notices import record_and_deliver_payment_failure
        with tenant_context(deck):
            summary = record_and_deliver_payment_failure(deck, invoice_id=obj.get('id') or 'unknown')
        return f'{deck.schema_name}: {summary}'

    return f'ignored event type {event_type}'
