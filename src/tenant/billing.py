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
import json
import logging
from datetime import datetime, time as dt_time, timedelta, timezone as dt_timezone

import stripe

from django.conf import settings
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import localdate

logger = logging.getLogger(__name__)

# Cap outbound Stripe HTTP time: webhook handlers retrieve subscriptions inside
# the request's DB transaction (needed for the StripeEventLog dedupe + rollback
# semantics), so the SDK's default read timeout (80s) could pin a DB connection
# through a slow Stripe response. 15s is generous for single-object calls.
# (_http_client is the SDK's internal module; under an incompatible SDK layout
# the guard leaves Stripe's default timeout active and boot proceeds.)
try:
    from stripe import _http_client as _stripe_http_client

    stripe.default_http_client = _stripe_http_client.new_default_http_client(timeout=15)
except (ImportError, AttributeError):  # pragma: no cover -- requires a different SDK layout
    pass

# Stripe rejects a subscription trial_end closer than 48 hours out; the extra
# hour absorbs clock skew and request latency so a boundary-day checkout can't
# fail at Stripe after passing our check
CHECKOUT_TRIAL_END_MINIMUM = timedelta(hours=49)

# How long the subscription page's plan summary (product name, price, cadence)
# may serve from cache before re-asking Stripe. The billing write paths clear
# the cache on sync, so this only bounds staleness for dashboard-side edits
# (e.g. a renamed product) that fire no event we act on.
PLAN_SUMMARY_CACHE_SECONDS = 60 * 15


def to_plain_dict(stripe_obj):
    """A stripe-python object (or a dict) as plain nested dicts/lists.

    stripe-python 15.x objects support indexing but are NOT dicts: ``.get()``
    raises AttributeError. The handlers and sync code are written dict-style,
    which every test exercised with plain-dict doubles, so the mismatch only
    surfaced on staging's first real webhook delivery (500 on every event,
    2026-08-09). Converting at each SDK boundary keeps the dict-style code and
    the test doubles honest; ``str()`` of a Stripe object is its full JSON.

    Args:
        stripe_obj: A stripe-python object, or an already-plain dict.

    Returns:
        dict: The same data as plain nested dicts/lists.
    """
    if isinstance(stripe_obj, dict):
        return stripe_obj
    return json.loads(str(stripe_obj))


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
        # stamp the subscription too, so webhook subscription events (PR 7)
        # self-identify without a lookup; a mid-trial deck's remaining free time
        # rides along as trial_end, so the subscription starts `trialing` until
        # the deck's existing trial ends
        subscription_data={
            'metadata': {'schema_name': deck.schema_name},
            **({'trial_end': int(trial_end.timestamp())} if trial_end else {}),
        },
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


def stamp_customer_description(deck, customer_id):
    """Best-effort: label the Stripe Customer with the deck it pays for.

    Checkout creates the Customer with only the payer's email, so the dashboard's
    Customers list gives no hint which deck a customer belongs to (maintainer
    request, 2026-08-09). Stamping the schema name into the description (and
    searchable metadata) fixes that at the moment a customer is
    first linked to a deck. Purely cosmetic, so a Stripe error is logged and
    swallowed: it must never fail the webhook or the post-checkout reconcile
    that calls it.

    Args:
        deck (Tenant): The deck the customer was just linked to.
        customer_id (str): The Stripe customer id (cus_...).
    """
    try:
        stripe.Customer.modify(
            customer_id,
            api_key=settings.STRIPE_SECRET_KEY,
            description=deck.schema_name,
            metadata={'schema_name': deck.schema_name},
        )
    except stripe.StripeError as e:
        logger.warning('could not stamp deck description on Stripe customer %s: %s', customer_id, e)


def _plan_summary_cache_key(schema_name, subscription_id):
    """Cache key for one deck's plan summary, keyed on the linked subscription."""
    return f'stripe-plan-summary:{schema_name}:{subscription_id}'


def clear_plan_summary_cache(schema_name, *subscription_ids):
    """Drop cached plan summaries so the subscription page re-fetches from Stripe.

    Called from the billing write paths (checkout reconciliation and
    ``Tenant.sync_from_stripe_subscription``) so a plan switched in the billing
    portal shows on the page as soon as its webhook syncs, rather than after the
    cache TTL runs out.

    Args:
        schema_name (str): The deck's schema.
        *subscription_ids: Subscription ids whose cached summaries may exist
            (typically the event's and the previously linked one); falsy and
            duplicate entries are skipped.
    """
    for subscription_id in set(subscription_ids):
        if subscription_id:
            cache.delete(_plan_summary_cache_key(schema_name, subscription_id))


def _plan_summary_from_subscription(subscription):
    """Condense a retrieved subscription (price + product expanded) to display parts.

    Args:
        subscription (dict): A Stripe Subscription with ``items.data.price.product``
            expanded (or an equivalent test double).

    Returns:
        dict | None: ``{'name': ..., 'renewal_phrase': ...}`` -- the Product's name
        and a cadence-plus-price phrase like "renewed annually at $75.00 per year"
        or "renewed every 6 months at $50.00" (empty string when the price has no
        recurrence). None when there's no expanded product name to show.
    """
    data = (subscription.get('items') or {}).get('data') or []
    price = (data[0].get('price') or {}) if data else {}
    product = price.get('product')
    name = product.get('name') if isinstance(product, dict) else None
    if not name:
        return None

    recurring = price.get('recurring') or {}
    interval = recurring.get('interval')
    count = recurring.get('interval_count') or 1
    if interval == 'year' and count == 1:
        cadence, per_suffix = 'renewed annually', ' per year'
    elif interval == 'month' and count == 1:
        cadence, per_suffix = 'renewed monthly', ' per month'
    elif interval:
        cadence, per_suffix = f'renewed every {count} {interval}s', ''
    else:  # a one-time price shouldn't arise on a subscription, but Stripe allows odd data
        cadence, per_suffix = '', ''

    amount = price.get('unit_amount')
    money = ''
    if amount is not None:
        currency = (price.get('currency') or '').lower()
        rendered = f'{amount / 100:,.2f}'
        money = f'${rendered}' if currency in ('', 'usd') else f'{rendered} {currency.upper()}'

    if cadence and money:
        phrase = f'{cadence} at {money}{per_suffix}'
    else:
        # a cadence alone still reads fine; a price with no cadence would dangle, so drop it
        phrase = cadence
    return {'name': name, 'renewal_phrase': phrase}


def subscription_plan_summary(deck):
    """What the deck's linked Stripe subscription buys, for the status line, or None.

    Retrieves the subscription with its price and product expanded and condenses
    it via :func:`_plan_summary_from_subscription` to the Product name plus a
    renewal phrase (e.g. "Bytedeck Subscription - 40 Students" / "renewed
    annually at $75.00 per year"). The result is cached for
    PLAN_SUMMARY_CACHE_SECONDS per (deck, subscription) and cleared by the
    billing write paths, so the page doesn't call Stripe on every load yet shows
    a portal plan switch as soon as its webhook syncs.

    Returns None -- the page then renders its usual copy with no plan info --
    when the deck has no linked subscription, no secret key is configured, the
    retrieve fails (logged, swallowed: a Stripe hiccup must not break the page),
    or the data carries no product name.

    Args:
        deck (Tenant): The current deck.

    Returns:
        dict | None: ``{'name': str, 'renewal_phrase': str}`` or None.
    """
    if not deck.stripe_subscription_id or not settings.STRIPE_SECRET_KEY:
        return None
    cache_key = _plan_summary_cache_key(deck.schema_name, deck.stripe_subscription_id)
    summary = cache.get(cache_key)
    if summary is not None:
        return summary
    try:
        subscription = to_plain_dict(stripe.Subscription.retrieve(
            deck.stripe_subscription_id, api_key=settings.STRIPE_SECRET_KEY,
            expand=['items.data.price.product'],
        ))
    except stripe.StripeError as e:
        logger.warning('could not fetch the plan summary for %s: %s', deck.schema_name, e)
        return None
    summary = _plan_summary_from_subscription(subscription)
    if summary is not None:
        cache.set(cache_key, summary, PLAN_SUMMARY_CACHE_SECONDS)
    return summary


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

    session = to_plain_dict(stripe.checkout.Session.retrieve(
        session_id, api_key=settings.STRIPE_SECRET_KEY, expand=['subscription'],
    ))
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
    # stamp only on a fresh link, so repeat polls of the status endpoint don't
    # re-write the customer on every poll
    newly_linked = bool(updates['stripe_customer_id']) and deck.stripe_customer_id != updates['stripe_customer_id']
    Tenant.objects.filter(schema_name=deck.schema_name).update(**updates)
    invalidate_current_deck_cache(deck.schema_name)  # the banner should update immediately
    clear_plan_summary_cache(deck.schema_name, deck.stripe_subscription_id, updates['stripe_subscription_id'])
    if newly_linked:
        stamp_customer_description(deck, updates['stripe_customer_id'])
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
        cap = int(raw)
    except (TypeError, ValueError):
        return None
    # -1 = unlimited (the Tenant field's own convention); anything below it is
    # meaningless metadata that would read as a cap every count exceeds, so it
    # resolves to None like any other malformed value (review find on #2110)
    return cap if cap >= -1 else None


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


def _invoice_subscription_id(invoice):
    """The subscription an invoice belongs to, or None.

    Older Stripe API versions carry a top-level ``subscription`` on the invoice;
    newer ones moved the reference under ``parent.subscription_details``. Same
    dual-shape handling as :func:`subscription_period_end_date`.
    """
    sub_id = invoice.get('subscription')
    if sub_id:
        return sub_id
    details = (invoice.get('parent') or {}).get('subscription_details') or {}
    return details.get('subscription') or None


def _sync_deck_from_subscription_id(deck, subscription_id):
    """Retrieve a subscription from Stripe and run the single-write-path sync.

    Skips (with a log summary) when ``STRIPE_SECRET_KEY`` is unset: a server
    configured with only the webhook secret can still absorb events that sync
    straight from their payloads, but it cannot retrieve, and an exception here
    would turn into a 500 that Stripe retries for days (review find on #2110).

    Args:
        deck (Tenant): The deck whose billing state the subscription drives.
        subscription_id (str): The Stripe subscription id (sub_...) to retrieve.

    Returns:
        str: A short human-readable summary for the caller's log/audit trail.
    """
    if not settings.STRIPE_SECRET_KEY:
        return 'STRIPE_SECRET_KEY unset; retrieve skipped'
    subscription = to_plain_dict(stripe.Subscription.retrieve(subscription_id, api_key=settings.STRIPE_SECRET_KEY))
    return deck.sync_from_stripe_subscription(subscription)


def handle_webhook_event(event):
    """Dispatch one verified Stripe webhook event.

    Handlers are thin translators (plan §5.2): resolve the deck, then call one
    named method -- ``Tenant.sync_from_stripe_subscription`` for anything that
    changes billing state, the notices machinery for payment failures. Unhandled
    event types are logged and acknowledged. Idempotence (duplicate delivery)
    is enforced by the caller via StripeEventLog before this runs.

    Args:
        event: The verified Stripe Event, as the SDK's Event object or an
            equivalent plain dict (converted internally via to_plain_dict).

    Returns:
        tuple[str, str]: ``(schema_name, summary)`` -- the resolved deck's schema
        (empty string when no deck resolved) as structured data for the event
        log's audit trail, and a human-readable summary for the worker log.
    """
    from django_tenants.utils import tenant_context

    # accept the SDK's Event object as well as a plain dict: everything below
    # (and every handler) speaks dict
    event = to_plain_dict(event)
    event_type = event.get('type', '')
    obj = (event.get('data') or {}).get('object') or {}
    metadata = obj.get('metadata') or {}

    if event_type == 'checkout.session.completed':
        deck = _resolve_deck(schema_name=obj.get('client_reference_id') or metadata.get('schema_name'),
                             customer_id=obj.get('customer'))
        if deck is None:
            return '', 'no deck resolved'
        # Subscription sync first (the payload carries the subscription only as
        # an id string, so this retrieves it): the sync's identity guard rules
        # on whether this session's subscription is the deck's linked one, and
        # the customer link below follows that same ruling.
        parts = []
        session_sub = obj.get('subscription') or ''
        if session_sub:
            parts.append(_sync_deck_from_subscription_id(deck, session_sub))
        if obj.get('customer'):
            from django.db.models import Q

            from tenant.models import Tenant
            # Identity-guarded customer link, applied as one conditional UPDATE
            # (atomic, so no read-then-write race): the customer is linked only
            # when this session's subscription IS the deck's linked subscription,
            # or the deck is entirely unlinked (the initial link on a server that
            # cannot retrieve). A delayed event for a superseded checkout must
            # not overwrite a newer customer link -- the same identity principle
            # as sync_from_stripe_subscription (review find on #2110).
            guard = Q(stripe_customer_id='', stripe_subscription_id='')
            if session_sub:
                guard |= Q(stripe_subscription_id=session_sub)
            linked = Tenant.objects.filter(guard, pk=deck.pk).update(stripe_customer_id=obj['customer'])
            if linked and deck.stripe_customer_id != obj['customer']:
                # a fresh link (not a re-delivery rewriting the same id): label the
                # customer with its deck so the dashboard's Customers list is legible
                stamp_customer_description(deck, obj['customer'])
            parts.append('linked customer' if linked else 'customer link kept (session not for the linked subscription)')
        else:
            # a session without a customer must not CLEAR a stored link
            # (review find on #2110)
            parts.append('no customer on session')
        return deck.schema_name, '; '.join(parts)

    if event_type in ('customer.subscription.created', 'customer.subscription.updated', 'customer.subscription.deleted'):
        deck = _resolve_deck(schema_name=metadata.get('schema_name'),
                             customer_id=obj.get('customer'), subscription_id=obj.get('id'))
        if deck is None:
            return '', 'no deck resolved'
        return deck.schema_name, deck.sync_from_stripe_subscription(obj)

    if event_type == 'invoice.paid':
        subscription_id = _invoice_subscription_id(obj)
        deck = _resolve_deck(customer_id=obj.get('customer'), subscription_id=subscription_id)
        if deck is None:
            return '', 'no deck resolved'
        if not subscription_id:
            return deck.schema_name, 'invoice without subscription, ignored'
        return deck.schema_name, _sync_deck_from_subscription_id(deck, subscription_id)

    if event_type == 'invoice.payment_failed':
        deck = _resolve_deck(customer_id=obj.get('customer'), subscription_id=_invoice_subscription_id(obj))
        if deck is None:
            return '', 'no deck resolved'
        # Delivery resolves the owner/staff from the deck's schema, and respects
        # the same report-only rollout gate as the reminder engine.
        from tenant.notices import record_and_deliver_payment_failure
        with tenant_context(deck):
            summary = record_and_deliver_payment_failure(deck, invoice_id=obj.get('id') or 'unknown')
        return deck.schema_name, summary

    return '', f'ignored event type {event_type}'
