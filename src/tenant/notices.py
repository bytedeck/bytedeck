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

from tenant.models import DeckNotice, TRIAL_MAX_ACTIVE_USERS


# expiry thresholds, most specific first: the first unfired one whose window has
# been entered is the one that fires (so a deck first seen at 10 days out gets
# ONE notice -- d14 -- not a d30+d14 double)
EXPIRY_THRESHOLDS = (('d7', 7), ('d14', 14), ('d30', 30))

LIMIT_WARNING_FRACTION = 0.8

# How far back a suspension episode may have begun and still get its one-time
# cap reset when the nightly task first sees it: covers multi-day beat outages
# without rewriting caps on decks that were already suspended long before (whose
# admins may have hand-adjusted the cap since -- exactly what the reset must
# never clobber).
CAP_RESET_CATCHUP_DAYS = 7


def _unfired(deck, kind, threshold, period_key):
    """Whether this exact notice hasn't been recorded yet."""
    return not DeckNotice.objects.filter(tenant=deck, kind=kind, threshold=threshold, period_key=period_key).exists()


def reset_cap_on_new_suspension(deck):
    """Once per suspension episode, write the trial default back into the deck's
    ``max_active_users`` -- the "revert to trial limits" moment (#1734).

    Enforcement, not communication: unlike the notices below this is NOT gated
    by ``settings.DECK_NOTICES_ENABLED``. The cap is applied exactly once per
    episode (a `DeckNotice` ledger row with threshold 'cap-reset' keyed to the
    episode's first suspended day), so an admin adjustment made afterwards --
    lower for a wind-down, higher for a comp -- always sticks
    (maintainer decision on #2178). Episodes that began more than
    CAP_RESET_CATCHUP_DAYS ago are recorded but NOT reset: they predate this
    feature (or a long beat outage), and their caps may already be deliberate.

    Runs inside the deck's tenant context via ``deck_status_check``. Returns a
    short summary string for the worker log.
    """
    from django.utils.timezone import timedelta

    from tenant.models import GRACE_PERIOD_DAYS, Tenant
    from tenant.utils import invalidate_current_deck_cache

    if not deck.is_suspended:
        return 'not suspended'

    # First day of this suspension episode: the day after the LAST clock lapsed
    # (trials end at trial_end_date; paid access ends after the grace window).
    last_covered_days = []
    if deck.trial_end_date:
        last_covered_days.append(deck.trial_end_date)
    if deck.paid_until:
        last_covered_days.append(deck.paid_until + timedelta(days=GRACE_PERIOD_DAYS))
    episode_start = max(last_covered_days) + timedelta(days=1)

    _, created = DeckNotice.objects.get_or_create(
        tenant=deck, kind=DeckNotice.KIND_SUSPENDED, threshold='cap-reset', period_key=str(episode_start),
    )
    if not created:
        return 'cap already reset this episode'
    if localdate() - episode_start > timedelta(days=CAP_RESET_CATCHUP_DAYS):
        return f'episode began {episode_start}, before the catch-up window; cap left alone'
    if deck.max_active_users == TRIAL_MAX_ACTIVE_USERS:
        return 'cap already at the trial default'

    old_cap = deck.max_active_users
    # targeted update (not save()) so a concurrent admin edit to another column
    # can't be clobbered by this stale instance
    Tenant.objects.filter(pk=deck.pk).update(max_active_users=TRIAL_MAX_ACTIVE_USERS)
    deck.max_active_users = TRIAL_MAX_ACTIVE_USERS
    invalidate_current_deck_cache(deck.schema_name)
    return f'cap reset {old_cap} -> {TRIAL_MAX_ACTIVE_USERS}'


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
    from django.utils.timezone import timedelta

    from tenant.models import GRACE_PERIOD_DAYS, INACTIVE_DELETE_DAYS

    from tenant.tasks import send_email_message

    config = SiteConfig.get()
    days = deck.days_until_expiry
    # the day the deck's suspension began (or would begin): the day after its LAST
    # covered day -- trials end at trial_end_date, paid access after the grace window
    last_covered_days = []
    if deck.trial_end_date:
        last_covered_days.append(deck.trial_end_date)
    if deck.paid_until:
        last_covered_days.append(deck.paid_until + timedelta(days=GRACE_PERIOD_DAYS))
    # is_suspended requires at least one date field, so the list is never empty here
    suspended_since = max(last_covered_days) + timedelta(days=1) if deck.is_suspended else None
    # The scheduled deletion day under the suspension policy: INACTIVE_DELETE_DAYS
    # after the deletion CLOCK starts; the suspended email LEADS with it (maintainer
    # request, 2026-07-30: put the bottom line up front). The clock never starts
    # before the deck was actually WARNED (maintainer decision, 2026-07-31): a
    # legacy deck whose dates lapsed long before this machinery went live gets its
    # full year measured from its first suspended notice (this episode's ledger
    # row, written moments before delivery; sent-today fallback covers a
    # not-yet-committed row), never from a backdated lapse date.
    deletion_date = None
    if suspended_since:
        first_warned_row = DeckNotice.objects.filter(
            tenant=deck, kind=DeckNotice.KIND_SUSPENDED, threshold='suspended',
            period_key=str(max(last_covered_days)),
        ).order_by('sent_on').first()
        warned_on = first_warned_row.sent_on if first_warned_row else localdate()
        deletion_date = max(suspended_since, warned_on) + timedelta(days=INACTIVE_DELETE_DAYS)
    context = {
        'deck': deck,
        'config': config,
        'days': days,
        'cap': deck.effective_max_active_users,
        # what a fresh suspension will RESET the cap to (reset_cap_on_new_suspension)
        # -- the grace email predicts it, and can't derive it from `cap`, which is
        # still the paid cap during grace
        'trial_cap': TRIAL_MAX_ACTIVE_USERS,
        'count': deck.active_user_count,
        # every date the owner could want (maintainer request, 2026-07-25): when the
        # paid period ended/ends, how long ago, when the grace window closes, and --
        # for suspended decks -- the day the suspension began. None when not applicable.
        'grace_days': GRACE_PERIOD_DAYS,
        'grace_end_date': deck.paid_until + timedelta(days=GRACE_PERIOD_DAYS) if deck.paid_until else None,
        'grace_days_left': deck.grace_days_remaining,
        'expired_days_ago': -days if days is not None and days < 0 else None,
        'suspended_since': suspended_since,
        'deletion_date': deletion_date,
        'deletion_days_left': (deletion_date - localdate()).days if deletion_date else None,
        # the deck's own staff-facing subscription page (PR 6) -- emails go to the
        # deck owner, who is staff; the page falls back to the public subscribe
        # flatpage when Stripe isn't configured
        'subscribe_url': deck.get_root_url() + reverse('decks:subscription'),
        'archive_help_url': deck.get_root_url() + reverse('courses:archive_students_help'),
    }
    # Each label must read naturally in BOTH places it appears (kept deliberately
    # coupled, maintainer decision 2026-07-31): the email subject
    # "{site}: {label}" and the in-app notification sentence "sent a {label}."
    templates = {
        DeckNotice.KIND_EXPIRY: ('expiry_reminder', 'subscription expiry reminder'),
        DeckNotice.KIND_LIMIT: ('limit_warning', 'current-student limit warning'),
        DeckNotice.KIND_SUSPENDED: ('suspended_notice', 'deck suspended warning'),
    }
    template_name, verb = templates[kind]
    subject = f"{config.site_name_short}: {verb}"
    message = render_to_string(f'tenant/email/{template_name}.html', context)

    # In-app notification first (DB-only, rolls back cleanly with the ledger row);
    # deck_owner is a non-nullable PROTECT FK, so there is always an owner to notify.
    # The sender is the ByteDeck support account (displayed as "Bytedeck" by the
    # notifications app), falling back to deck_ai on older decks that predate the
    # support account (maintainer request, 2026-07-31: these notices come from
    # Bytedeck, not from the deck owner's own account). Fallback edge: if deck_ai
    # IS the owner (the seeded default on decks that never set a dedicated AI
    # user), the notifications app skips the self-notification -- such owners are
    # still covered by the email and the status banner.
    from django.contrib.auth import get_user_model
    User = get_user_model()
    staff = User.objects.filter(is_staff=True, is_active=True)
    sender = User.objects.filter(username=settings.TENANT_DEFAULT_ADMIN_USERNAME, is_active=True).first() or config.deck_ai
    notify.send(
        sender,
        recipient=config.deck_owner,
        affected_users=staff,
        verb=f'sent a {verb}.',
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
