"""The deck reminder engine (epic #1729 PR 5, closes #1733).

Evaluates, records, and delivers deck status notices -- run per deck by the
nightly ``deck_status_check`` task, right after the cached counts refresh:

* EXPIRY cadence: a reminder at 30, 14, and 7 days before the governing deadline
  (trial end, or paid_until), then daily through the final week and the paid
  grace window. At most one expiry notice per deck per day.
* LIMIT warnings: when the current-student count reaches 80% / 100% of the
  effective cap; re-armed monthly so owners are reminded but not spammed.
* SUSPENDED: once per suspension (a deck whose clocks all lapsed).

Delivery is two-channel: an email to the deck owner (via the existing
``send_email_message`` task) and an in-app notification from the deck AI to the
owner and staff. The persistent pressure comes from the status banner (PR 3);
in-app notifications are transient by design (90-day purge).

ROLLOUT (plan §10.2): everything is gated by ``settings.DECK_NOTICES_ENABLED``,
default off. While off the engine runs REPORT-ONLY -- it logs what it *would*
send (visible in the worker log / task result) but writes no ledger rows and
sends nothing, so a production cycle can be reviewed before enabling.
"""
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import localdate

from notifications.signals import notify
from siteconfig.models import SiteConfig

from tenant.models import DeckNotice
from tenant.utils import get_public_subscribe_url


# expiry thresholds, most specific first: the first unfired one whose window has
# been entered is the one that fires (so a deck first seen at 10 days out gets
# ONE notice -- d14 -- not a d30+d14 double)
EXPIRY_THRESHOLDS = (('d7', 7), ('d14', 14), ('d30', 30))

LIMIT_WARNING_FRACTION = 0.8


def _unfired(deck, kind, threshold, period_key):
    """Whether this exact notice hasn't been recorded yet."""
    return not DeckNotice.objects.filter(tenant=deck, kind=kind, threshold=threshold, period_key=period_key).exists()


def evaluate_deck_notices(deck):
    """Return the notices due for `deck` today, as (kind, threshold, period_key) tuples.

    Pure evaluation -- no ledger writes, no delivery. Reads the deck's derived
    status properties and the DeckNotice ledger.
    """
    due = []
    today = localdate()

    # --- suspension: once per suspension episode ---------------------------------
    if deck.is_suspended:
        lapsed_clocks = [d for d in (deck.trial_end_date, deck.paid_until) if d is not None]
        period_key = str(max(lapsed_clocks))
        if _unfired(deck, DeckNotice.KIND_SUSPENDED, 'suspended', period_key):
            due.append((DeckNotice.KIND_SUSPENDED, 'suspended', period_key))
    else:
        # --- expiry cadence (not for suspended decks; their deadline is history) --
        days = deck.days_until_expiry
        if days is not None and days <= EXPIRY_THRESHOLDS[-1][1]:
            deadline = deck.paid_until if deck.subscription_active else deck.trial_end_date
            period_key = str(deadline)
            # the first (most specific) milestone whose window we're inside governs --
            # broader milestones are superseded, never fired late. The guard above
            # guarantees at least the broadest window matches.
            threshold = [t for t, t_days in EXPIRY_THRESHOLDS if days <= t_days][0]
            fired_milestone = _unfired(deck, DeckNotice.KIND_EXPIRY, threshold, period_key)
            if fired_milestone:
                due.append((DeckNotice.KIND_EXPIRY, threshold, period_key))
            # daily through the final week and the grace window (days goes negative),
            # but never two expiry notices on the same day
            if not fired_milestone and days <= EXPIRY_THRESHOLDS[0][1]:
                threshold = f'daily-{today}'
                if _unfired(deck, DeckNotice.KIND_EXPIRY, threshold, period_key):
                    due.append((DeckNotice.KIND_EXPIRY, threshold, period_key))

    # --- current-student limit warnings, re-armed monthly ------------------------
    cap = deck.effective_max_active_users
    if cap > 0:
        count = deck.active_user_count  # cached, refreshed moments earlier by the task
        month_key = today.strftime('%Y-%m')
        if count >= cap:
            if _unfired(deck, DeckNotice.KIND_LIMIT, 'pct100', month_key):
                due.append((DeckNotice.KIND_LIMIT, 'pct100', month_key))
        elif count >= cap * LIMIT_WARNING_FRACTION:
            if _unfired(deck, DeckNotice.KIND_LIMIT, 'pct80', month_key):
                due.append((DeckNotice.KIND_LIMIT, 'pct80', month_key))

    return due


def process_deck_notices(deck):
    """Evaluate and (unless report-only) record + deliver the notices due for `deck`.

    Must run inside the deck's tenant context (delivery resolves the owner and
    staff from the schema). Returns a short summary string for the worker log.
    """
    due = evaluate_deck_notices(deck)
    if not due:
        return "no notices due"

    labels = ', '.join(f'{kind}/{threshold}' for kind, threshold, _ in due)
    if not settings.DECK_NOTICES_ENABLED:
        return f"REPORT-ONLY (DECK_NOTICES_ENABLED off): would send [{labels}]"

    sent = 0
    for kind, threshold, period_key in due:
        # record + deliver atomically: if delivery raises, the ledger row rolls back
        # so the next nightly run retries instead of the notice being recorded but
        # never sent (_deliver orders its side effects so the non-rollbackable
        # email enqueue happens last)
        with transaction.atomic():
            _, created = DeckNotice.objects.get_or_create(
                tenant=deck, kind=kind, threshold=threshold, period_key=period_key
            )
            if not created:  # lost a race with a concurrent run; that run delivered it
                continue
            _deliver(deck, kind)
        sent += 1
    return f"sent {sent} notice(s): [{labels}]"


def _deliver(deck, kind):
    """Send one notice through both channels: owner email + in-app notification."""
    from tenant.tasks import send_email_message

    config = SiteConfig.get()
    context = {
        'deck': deck,
        'config': config,
        'days': deck.days_until_expiry,
        'cap': deck.effective_max_active_users,
        'count': deck.active_user_count,
        'subscribe_url': get_public_subscribe_url(),
        'archive_help_url': deck.get_root_url() + reverse('courses:archive_students_help'),
    }
    templates = {
        DeckNotice.KIND_EXPIRY: ('expiry_reminder', 'trial/subscription expiry reminder'),
        DeckNotice.KIND_LIMIT: ('limit_warning', 'current-student limit warning'),
        DeckNotice.KIND_SUSPENDED: ('suspended_notice', 'deck suspended'),
    }
    template_name, verb = templates[kind]
    subject = f"{config.site_name_short}: {verb}"
    message = render_to_string(f'tenant/email/{template_name}.html', context)

    # In-app notification first (DB-only, rolls back cleanly with the ledger row);
    # deck_owner is a non-nullable PROTECT FK, so there is always an owner to notify.
    # Edge: if deck_ai IS the owner (the seeded default on decks that never set a
    # dedicated AI user), the notifications app skips the self-notification -- such
    # owners are still covered by the email and the status banner.
    from django.contrib.auth import get_user_model
    staff = get_user_model().objects.filter(is_staff=True, is_active=True)
    notify.send(
        config.deck_ai,
        recipient=config.deck_owner,
        affected_users=staff,
        verb=f'sent a {verb} for this deck:',
        icon="<i class='fa fa-lg fa-fw fa-credit-card text-warning'></i>",
    )

    # Email enqueue last: it can't be rolled back, so it only runs once everything
    # else succeeded. A broker failure here raises and rolls the whole notice back
    # for a clean retry on the next nightly run; the worst case is a duplicate
    # email if the commit itself then fails -- preferable to a committed notice
    # whose email was never handed off.
    owner_email = deck.get_owner_email_cached()
    if owner_email:
        send_email_message.apply_async(
            kwargs={'subject': subject, 'message': message, 'recipient_list': [owner_email]},
            queue='default',
        )
