"""Stripe glue for deck subscriptions (epic #1729 PR 6).

All Stripe API access for the subscription page lives here so the views stay
thin and tests can mock a single seam (``tenant.billing.stripe``). Nothing in
this module is reachable when billing isn't configured: the page checks
:func:`billing_configured` first and falls back to the public subscribe page.

The checkout flow is deliberately webhook-free in this PR: after Checkout
redirects back, the "activating" page polls a status endpoint that calls
:func:`reconcile_checkout_session`, which reads the session/subscription state
from Stripe and links/extends the deck itself. The webhook endpoint (plan PR 7)
later takes over renewals and payment failures; this reconciliation stays as
the never-assume-the-webhook-landed fallback (plan §5.4).
"""
from datetime import datetime, time as dt_time, timedelta, timezone as dt_timezone

import stripe

from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localdate

# Stripe rejects a subscription trial_end closer than 48 hours out; the extra
# hour absorbs clock skew and request latency so a boundary-day checkout can't
# fail at Stripe after passing our check
CHECKOUT_TRIAL_END_MINIMUM = timedelta(hours=49)


def billing_configured():
    """Whether Stripe checkout can run: the secret key and the subscription Price are set.

    The publishable key isn't required by the redirect-based Checkout flow, and the
    webhook secret only matters to the webhook endpoint (PR 7).
    """
    return bool(settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID)


def _subscription_page_url(deck):
    """Absolute URL of this deck's subscription page (Stripe needs absolute URLs)."""
    return deck.get_root_url() + reverse('decks:subscription')


def checkout_trial_end(deck):
    """When this deck subscribes mid-trial, the aware datetime its Stripe trial
    should run until, or None when a plain (bill-now) checkout is right.

    A mid-trial subscriber keeps their remaining free time (maintainer decision,
    2026-08-06): checkout passes this as ``subscription_data.trial_end`` so the
    subscription starts ``trialing``, the card is collected now, and the first
    charge lands when the deck's existing trial ends, auto-renewing from then
    on. The deck's trial covers THROUGH ``trial_end_date``, so the Stripe trial
    runs to local midnight after that day (settings.TIME_ZONE).

    None when the TRIAL clock isn't the deck's governing (latest) clock
    (#1734 B4: with both dates set the later one governs, and a tie speaks
    subscription language), and None when the trial ends within
    CHECKOUT_TRIAL_END_MINIMUM (Stripe requires trial_end at least 48 hours in
    the future, so a nearly-over or lapsed-into-grace trial just bills
    immediately: there is little or no free time left to preserve).

    Args:
        deck (Tenant): The current deck.

    Returns:
        datetime | None: The aware trial-end moment to send to Stripe, or None.
    """
    if not deck.governing_clock_is_trial:
        return None
    end = timezone.make_aware(datetime.combine(deck.governing_deadline + timedelta(days=1), dt_time.min))
    if end < timezone.now() + CHECKOUT_TRIAL_END_MINIMUM:
        return None
    return end


def create_checkout_session(deck):
    """Create a subscription Checkout Session for an unlinked deck; return its URL.

    The deck is identified to Stripe three ways (client_reference_id, metadata,
    and the customer email), so the webhook (PR 7) and manual reconciliation can
    always find their way back to the schema. A mid-trial deck's remaining free
    time rides along as ``subscription_data.trial_end`` (see
    :func:`checkout_trial_end`). The idempotency key means a double-click or
    same-day retry with identical parameters reuses the same session instead of
    minting duplicates.

    Args:
        deck (Tenant): The current deck; must not already have a stripe_customer_id.

    Returns:
        str: The Stripe-hosted checkout URL to redirect the owner to.
    """
    trial_end = checkout_trial_end(deck)
    session = stripe.checkout.Session.create(
        api_key=settings.STRIPE_SECRET_KEY,
        mode='subscription',
        line_items=[{'price': settings.STRIPE_PRICE_ID, 'quantity': 1}],
        client_reference_id=deck.schema_name,
        customer_email=deck.get_owner_email_cached() or None,
        metadata={'schema_name': deck.schema_name},
        # the subscription starts `trialing` until the deck's existing trial ends
        **({'subscription_data': {'trial_end': int(trial_end.timestamp())}} if trial_end else {}),
        # Checkout substitutes the real session id into the literal placeholder
        success_url=deck.get_root_url() + reverse('decks:subscription_activating') + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=_subscription_page_url(deck),
        # Stripe rejects a reused idempotency key whose parameters changed, so the
        # trial variant carries the trial-end timestamp: a same-day retry after the
        # cutoff passed, or after an admin moved trial_end_date, gets a fresh key
        # while an identical retry still reuses the session
        idempotency_key=(
            f'deck-checkout-{deck.schema_name}-{localdate()}'
            + (f'-trial-{int(trial_end.timestamp())}' if trial_end else '')
        ),
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


def _subscription_period_end_date(subscription):
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
    paid_until = _subscription_period_end_date(subscription)
    if paid_until is not None:
        updates['paid_until'] = paid_until
    Tenant.objects.filter(schema_name=deck.schema_name).update(**updates)
    invalidate_current_deck_cache(deck.schema_name)  # the banner should update immediately
    return True
