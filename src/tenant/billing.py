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

# Currencies whose Stripe amounts are already whole units rather than cents
# (https://docs.stripe.com/currencies#zero-decimal): dividing by 100 would
# display a hundredth of the real price.
ZERO_DECIMAL_CURRENCIES = frozenset((
    'bif', 'clp', 'djf', 'gnf', 'jpy', 'kmf', 'krw', 'mga',
    'pyg', 'rwf', 'ugx', 'vnd', 'vuv', 'xaf', 'xof', 'xpf',
))

def deck_label(deck):
    """The deck's domain, the name its owner recognizes it by.

    Stripe's hosted pages show the product ("Bytedeck Subscription - 120
    Students"), which is identical for every deck on that tier, so an owner with
    several decks cannot tell which one they are paying for (production find,
    2026-08-10). This label goes into the places Stripe will display.

    Args:
        deck (Tenant): The deck being billed.

    Returns:
        str: The deck's primary domain, e.g. ``hackerspace.bytedeck.com``.
    """
    return deck.primary_domain_url


def _portal_configuration_cache_key(schema_name):
    """The cache key that held one deck's Billing Portal configuration id before
    the id lived on ``Tenant.stripe_portal_configuration_id``. Read only by the
    adoption branch of :func:`portal_configuration_id`, which promotes a still-
    cached id into the field so no duplicate configuration is created.

    Args:
        schema_name (str): The deck's schema name, which namespaces the entry so
            decks never read each other's configuration.

    Returns:
        str: The key, ``stripe-portal-config:{schema_name}``.
    """
    return f'stripe-portal-config:{schema_name}'


def portal_configuration_id(deck):
    """A Billing Portal configuration whose headline names this deck; None when
    one cannot be prepared.

    The portal is Stripe-hosted and takes no per-session copy, so naming the deck
    there means giving the session its own configuration. The configuration is
    cloned from the account's default so every feature the dashboard enables
    (cancel, update, invoice history, payment methods) is preserved, with only
    the headline replaced. Returning None makes the caller fall back to the
    account default: an unnamed portal is a far better outcome than no portal.

    Args:
        deck (Tenant): The deck being billed.

    Returns:
        str | None: The configuration id (``bpc_...``), or None if Stripe could
        not provide one.
    """
    if deck.stripe_portal_configuration_id:
        return deck.stripe_portal_configuration_id
    # adoption path: an id still sitting in the cache (where it lived before the
    # Tenant field existed) is promoted into the field rather than cloning a
    # duplicate configuration for a deck that already has one
    cache_key = _portal_configuration_cache_key(deck.schema_name)
    cached_id = cache.get(cache_key)
    if cached_id:
        _store_portal_configuration_id(deck, cached_id)
        cache.delete(cache_key)
        return cached_id
    try:
        defaults = stripe.billing_portal.Configuration.list(
            api_key=settings.STRIPE_SECRET_KEY, is_default=True, limit=1)
        default = defaults.data[0]
        # the login page is a flag, not copyable state: its url is read-only and
        # Stripe mints a fresh one per configuration, so only `enabled` carries over
        login_page = to_plain_dict(default.login_page) if getattr(default, 'login_page', None) else {}
        configuration = stripe.billing_portal.Configuration.create(
            api_key=settings.STRIPE_SECRET_KEY,
            # concurrent first visits both reach this create; the shared key makes
            # Stripe return ONE configuration to both, so the row converges on a
            # single id instead of orphaning a duplicate. Day-scoped like the
            # checkout key: within a day a replay with CHANGED parameters (an
            # operator cleared the field right after editing the account default)
            # is rejected by Stripe and lands in the except below, so that visit
            # falls back to the unnamed account-default portal until the key ages out
            idempotency_key=f'deck-portal-config-{deck.schema_name}-{localdate()}',
            business_profile={
                **to_plain_dict(default.business_profile),
                'headline': f'Subscription for {deck_label(deck)}',
            },
            features=to_plain_dict(default.features),
            **({'login_page': {'enabled': True}} if login_page.get('enabled') else {}),
            metadata={'schema_name': deck.schema_name},
        )
    except (stripe.StripeError, IndexError, AttributeError) as e:
        # no default configuration to clone, or Stripe refused the copy: the
        # portal still works without a configuration, so never block on this
        logger.warning("could not prepare a portal configuration for %s: %s", deck.schema_name, e)
        return None
    _store_portal_configuration_id(deck, configuration.id)
    return configuration.id


def _store_portal_configuration_id(deck, configuration_id):
    """Persist a deck's portal configuration id, on the row and the instance.

    A configuration is a permanent Stripe object, so once a deck has one it is
    reused forever; storing on the row is what stops every later portal visit
    from cloning another. The queryset update deliberately skips ``save()``
    (nothing else on the instance should be written from a billing lookup), and
    the in-memory attribute is set so the caller's instance agrees with the row.

    Args:
        deck (Tenant): The deck the configuration belongs to.
        configuration_id (str): The Stripe configuration id (``bpc_...``).

    Returns:
        None: The row and the instance are updated in place.
    """
    type(deck).objects.filter(pk=deck.pk).update(stripe_portal_configuration_id=configuration_id)
    deck.stripe_portal_configuration_id = configuration_id


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
    """Create a subscription Checkout Session for the deck; return its URL.

    The deck is identified to Stripe three ways (client_reference_id, metadata,
    and the customer identity), so the webhook (PR 7) and manual reconciliation
    can always find their way back to the schema. A first-time deck checks out
    under the owner's email (Stripe mints the customer); a deck that already
    has a ``stripe_customer_id`` (renewing after its old subscription fully
    ended) checks out AS that customer, keeping its saved cards and invoice
    history. A mid-trial deck's remaining free time rides along as
    ``subscription_data.trial_end`` (see :func:`checkout_trial_end`). The
    idempotency key means a double-click or same-day retry with identical
    parameters reuses the same session instead of minting duplicates.

    Args:
        deck (Tenant): The current deck.

    Returns:
        str: The Stripe-hosted checkout URL to redirect the owner to.
    """
    trial_end = checkout_trial_end(deck)
    session = stripe.checkout.Session.create(
        api_key=settings.STRIPE_SECRET_KEY,
        mode='subscription',
        line_items=[{'price': settings.STRIPE_PRICE_ID, 'quantity': 1}],
        client_reference_id=deck.schema_name,
        # a returning deck checks out as its EXISTING Stripe customer, so the
        # saved cards and invoice history carry over and the dashboard shows one
        # customer per deck; Stripe forbids passing customer and customer_email
        # together, so a first-time deck is identified by the owner's email
        **(
            {'customer': deck.stripe_customer_id}
            if deck.stripe_customer_id
            else {'customer_email': deck.get_owner_email_cached() or None}
        ),
        metadata={'schema_name': deck.schema_name},
        # stamp the subscription too, so webhook subscription events (PR 7)
        # self-identify without a lookup; a mid-trial deck's remaining free time
        # rides along as trial_end, so the subscription starts `trialing` until
        # the deck's existing trial ends
        subscription_data={
            'metadata': {'schema_name': deck.schema_name},
            # the deck this pays for, in Stripe's own displayable field: the
            # product name is the same for every deck on a tier, so this is what
            # tells an owner with several decks which one they are paying for
            'description': f'Deck: {deck_label(deck)}',
            **({'trial_end': int(trial_end.timestamp())} if trial_end else {}),
        },
        # the same fact on the payment page itself, above the pay button
        custom_text={'submit': {'message': f'You are subscribing the deck {deck_label(deck)}.'}},
        # Checkout substitutes the real session id into the literal placeholder
        success_url=deck.get_root_url() + reverse('decks:subscription_activating') + '?session_id={CHECKOUT_SESSION_ID}',
        cancel_url=_subscription_page_url(deck),
        # Stripe rejects a reused idempotency key whose parameters changed, so the
        # trial variant carries the trial-end timestamp: a same-day retry after the
        # cutoff passed, or after an admin moved trial_end_date, gets a fresh key
        # while an identical retry still reuses the session
        # a customer-bound (renewal) session has different parameters than an
        # email-identified one, so it gets its own key: a deck that abandoned an
        # unlinked checkout earlier the same day can still renew after linking.
        # The v2 generation marks the request shape that carries the deck label:
        # Stripe rejects a key replayed with different parameters for 24 hours,
        # so a same-day retry across a deploy must not reuse the older key.
        idempotency_key=(
            f'deck-checkout-v2-{deck.schema_name}-{localdate()}'
            + (f'-trial-{int(trial_end.timestamp())}' if trial_end else '')
            + (f'-{deck.stripe_customer_id}' if deck.stripe_customer_id else '')
        ),
    )
    return session.url


def has_manageable_subscription(deck):
    """Whether the deck's linked Stripe subscription is one the Billing Portal
    can still act on (renew, fix the card, switch plans, cancel).

    The portal manages LIVE subscriptions only. A fully canceled (or absent)
    subscription cannot be restarted there: the portal home shows just payment
    methods and invoice history, a dead end for an expired deck trying to come
    back (production find, 2026-08-09). Those decks need a fresh Checkout
    instead. Stripe is asked at call time so the answer matches what the portal
    will actually offer: ``past_due``/``unpaid`` subscriptions count as
    manageable (fixing the card in the portal is their cure), while
    ``canceled`` and ``incomplete_expired`` are dead ends.

    Args:
        deck (Tenant): The current deck.

    Returns:
        bool: True when the portal is the right destination for the manage
        button; False when a new Checkout is (no linked subscription, it no
        longer exists on this Stripe account/mode, or its status is terminal).

    Raises:
        stripe.StripeError: On any Stripe failure that leaves the
        subscription's state unknown (transport errors, and invalid requests
        other than the subscription not existing), so the caller shows its
        try-again message rather than starting a checkout.
    """
    if not deck.stripe_subscription_id:
        return False
    try:
        subscription = stripe.Subscription.retrieve(
            deck.stripe_subscription_id, api_key=settings.STRIPE_SECRET_KEY)
    except stripe.InvalidRequestError as error:
        # resource_missing means no such subscription for this key (deleted
        # upstream, or a test/live mode mismatch): nothing for the portal to
        # manage. Every OTHER invalid request (a malformed id, a bad parameter)
        # leaves the subscription's real state unknown, and treating unknown as
        # "gone" would offer a checkout that could duplicate a live
        # subscription, so those propagate to the caller's error handling.
        if error.code == 'resource_missing':
            return False
        raise
    return subscription.status not in ('canceled', 'incomplete_expired')


def create_portal_session(deck):
    """Create a Billing Portal session for a Stripe-linked deck; return its URL.

    The portal is where a linked deck renews, upgrades, changes card, or cancels
    -- Stripe hosts all of it; we only need the customer id. The session carries
    a configuration whose headline names the deck (see
    :func:`portal_configuration_id`), so an owner with several decks can see
    which one the portal is billing.

    Args:
        deck (Tenant): The current deck; must have a stripe_customer_id.

    Returns:
        str: The Stripe-hosted portal URL to redirect the owner to.
    """
    configuration_id = portal_configuration_id(deck)
    session = stripe.billing_portal.Session.create(
        api_key=settings.STRIPE_SECRET_KEY,
        customer=deck.stripe_customer_id,
        return_url=_subscription_page_url(deck),
        # a configuration headlined with the deck's domain; omitted when one
        # could not be prepared, which falls back to the account default
        **({'configuration': configuration_id} if configuration_id else {}),
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
    elif interval and count == 1:
        # a singular day/week cadence reads without the count ("renewed every week")
        cadence, per_suffix = f'renewed every {interval}', ''
    elif interval:
        cadence, per_suffix = f'renewed every {count} {interval}s', ''
    else:  # a one-time price shouldn't arise on a subscription, but Stripe allows odd data
        cadence, per_suffix = '', ''

    amount = price.get('unit_amount')
    money = ''
    if amount is not None:
        currency = (price.get('currency') or '').lower()
        # Stripe amounts are in the currency's SMALLEST unit: cents for most
        # currencies, but zero-decimal currencies (Stripe's documented list)
        # carry the whole amount already, so 7500 JPY is 7,500, not 75.00.
        if currency in ZERO_DECIMAL_CURRENCIES:
            rendered = f'{amount:,.0f}'
        else:
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


def subscription_auto_renews(subscription):
    """Whether this subscription will bill again on its own when its period ends.

    A live subscription renews unless its end is already scheduled: the owner
    turned on "cancel at period end" in the billing portal, or an operator set an
    explicit ``cancel_at``. Only a paying status counts as renewing: a
    ``past_due`` subscription is a renewal that IS ALREADY FAILING, and such a
    deck needs its expiry reminders back rather than a reassuring "renews
    automatically".

    Args:
        subscription (dict): A Stripe Subscription object (or test double).

    Returns:
        bool: True when the deck can expect this subscription to bill again.
    """
    if subscription.get('status') not in ('active', 'trialing'):
        return False
    return not subscription.get('cancel_at_period_end') and not subscription.get('cancel_at')


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
    # this write path bypasses sync_from_stripe_subscription, so it carries the
    # auto-renew fact itself: a deck fresh from checkout renews on its own, and
    # the lifecycle copy must say so from the first page load
    updates['stripe_auto_renews'] = subscription_auto_renews(subscription)
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
    stamp_subscription_description(deck, subscription)
    return deck.sync_from_stripe_subscription(subscription)


def stamp_subscription_description(deck, subscription):
    """Best-effort: label the Stripe subscription with the deck it pays for.

    Checkout sets this at creation, so this is the path that reaches everything
    older: legacy subscriptions linked by hand, and anything created before the
    label existed. Stripe shows the description alongside the plan, which is
    what tells an owner with several decks which one a subscription belongs to.
    Purely cosmetic, so a Stripe error is logged and swallowed: it must never
    fail the sync it rides along with.

    Args:
        deck (Tenant): The deck the subscription pays for.
        subscription (dict): The retrieved subscription, as a plain dict.
    """
    wanted = f'Deck: {deck_label(deck)}'
    if subscription.get('description') == wanted:
        return
    try:
        stripe.Subscription.modify(
            subscription['id'], api_key=settings.STRIPE_SECRET_KEY, description=wanted)
    except stripe.StripeError as e:
        logger.warning("could not label subscription %s for %s: %s", subscription.get('id'), deck.schema_name, e)


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
