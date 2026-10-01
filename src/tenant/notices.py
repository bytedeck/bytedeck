"""The deck reminder engine (epic #1729 PR 5, closes #1733).

Evaluates, records, and delivers deck status notices -- run per deck by the
nightly ``deck_status_check`` task, right after the cached counts refresh:

* EXPIRY cadence: a reminder at 30, 14, 7, and 1 days before the governing
  deadline (trial end, or paid_until). Four notices per period and nothing
  after: the deck keeps running through the grace window that follows, and the
  SUSPENDED notice closes the story out when that window ends.
* LIMIT notices: a heads-up when the current-student count reaches 90% and 95%
  of the effective cap and when one seat is left, then a warning when the cap is
  reached. Each level goes out at most once per semester, and never after a
  more severe one (#2824).
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
from django.utils.formats import date_format
from django.utils.timezone import localdate, timedelta

from notifications.signals import notify
from siteconfig.models import SiteConfig

from tenant.models import DeckNotice, GRACE_PERIOD_DAYS, TRIAL_MAX_ACTIVE_USERS


# expiry thresholds, most specific first: the first unfired one whose window has
# been entered is the one that fires (so a deck first seen at 10 days out gets
# ONE notice -- d14 -- not a d30+d14 double)
EXPIRY_THRESHOLDS = (('d1', 1), ('d7', 7), ('d14', 14), ('d30', 30))

# How many days before an auto-renewing subscription's renewal date its single
# heads-up goes out. Deliberately NOT Stripe's 7 days: every ByteDeck plan bills
# at 6 months or a year, so Stripe's own reminder (where the dashboard toggle is
# on) lands at 7 days for all of them. Going out at 14 makes ours the early,
# deck-specific heads-up and leaves Stripe's as a closer second nudge, instead of
# two emails about the same charge on the same day (#2586).
RENEWAL_NOTICE_DAYS = 14

# Current-student limit levels, least severe first. A deck that reaches one is sent the
# most severe level it has reached, unless that level or a more severe one already went
# out this semester: a deck that jumps from 85% to 96% gets only the 95% notice, and one
# that later drops back to 92% gets no 90% notice after it (#2824).
LIMIT_LEVELS = ('pct90', 'pct95', 'one-seat-left', 'pct100')


def _limit_level(count, cap):
    """The most severe current-student limit level a deck has reached.

    On a small cap one count can meet both a percentage and the last seat (on a cap of 10,
    the 9th student is at 90% and leaves one seat); the one-seat level wins, as the more
    specific news.

    Args:
        count (int): the deck's current students.
        cap (int): the deck's effective cap, a positive number of seats.

    Returns:
        str or None: one of LIMIT_LEVELS, or None when the deck has reached none of them.
    """
    if count >= cap:
        return 'pct100'
    if count and cap - count == 1:  # an empty deck with a one-seat cap isn't filling up
        return 'one-seat-left'
    if count * 100 >= cap * 95:
        return 'pct95'
    if count * 100 >= cap * 90:
        return 'pct90'
    return None


def _unfired(deck, kind, threshold, period_key):
    """Whether this exact notice hasn't been recorded yet."""
    return not DeckNotice.objects.filter(tenant=deck, kind=kind, threshold=threshold, period_key=period_key).exists()


def close_semester_on_new_suspension(deck):
    """Once per suspension episode, close the deck's open semester (#1734 redesign
    B2): the suspension moment ends the school term, so current students drop to
    zero. Every submission awaiting approval is returned first (maintainer
    decision, 2026-07-30: nothing stays stuck in a teacher's queue, and the
    normal close then works as-is), and a student's negative XP balance is
    recorded as zero rather than blocking the close.

    Enforcement, not communication: like the owner-only middleware (#2210) this
    is NOT gated by ``settings.DECK_NOTICES_ENABLED``. It runs exactly once per
    suspension episode (a DeckNotice ledger row with threshold
    'semester-close', keyed like the suspended notice to the episode's lapsed
    deadline), so an owner who deliberately opens a new semester while still
    suspended is not fought with. The ledger row and the close commit
    atomically: a crash rolls both back and the next nightly run retries.

    Runs inside the deck's tenant context; returns a short summary string for
    the worker log.
    """
    from courses.models import Semester
    from quest_manager.models import QuestSubmission

    if not deck.is_suspended:
        return 'not suspended'

    period_key = str(deck.governing_deadline)
    with transaction.atomic():
        _, created = DeckNotice.objects.get_or_create(
            tenant=deck, kind=DeckNotice.KIND_SUSPENDED, threshold='semester-close', period_key=period_key,
        )
        if not created:
            return 'semester close already handled this episode'

        # every open semester, not just the one the deck points at: suspension stops the
        # whole deck, so a second cohort's semester has to close with the first
        open_semesters = list(Semester.objects.open())
        if not open_semesters:
            # nothing was open; the episode is recorded so this isn't re-checked
            return 'no open semester to close'

        returned = 0
        closed = []
        for semester in open_semesters:
            # this semester's own pending approvals, cleared before it closes. Returning
            # only the deck-pointed semester's queue would leave a second open semester
            # blocked on its own, which rolls the whole suspension close back.
            for submission in QuestSubmission.objects.all_awaiting_approval(semester=semester):
                submission.mark_returned()
                returned += 1

            result = Semester.objects.complete_semester(semester, clamp_negative_xp=True)
            if result in (Semester.NO_OPEN_SEMESTER, Semester.QUEST_AWAITING_APPROVAL, Semester.STUDENTS_WITH_NEGATIVE_XP):
                # can't happen (submissions were just returned; negative XP is clamped),
                # but if it ever does, roll everything back and retry next run instead
                # of recording a close that didn't happen
                raise RuntimeError(f'semester close failed with sentinel {result}')
            closed.append(str(result))
    names = ', '.join(f'"{name}"' for name in closed)
    return f'closed semester {names} (returned {returned} awaiting-approval submission(s))'


def evaluate_deck_notices(deck):
    """Return the notices due for `deck` today, as (kind, threshold, period_key) tuples.

    Pure evaluation -- no ledger writes, no delivery. Reads the deck's derived
    status properties, the DeckNotice ledger, and (for the limit notices) the
    deck's open semesters, so it runs inside the deck's tenant context.

    A deck whose owner has a standing deletion request gets NO notices of any
    kind: asking for the deck to be deleted is the strongest possible signal
    that its owner is done hearing from us, and every notice this engine sends
    is a nudge toward keeping the deck alive. Canceling the request (from the
    subscription page) turns the notices back on.
    """
    if deck.deletion_requested_on is not None:
        return []

    due = []
    today = localdate()

    # --- suspension: once per suspension episode ---------------------------------
    if deck.is_suspended:
        period_key = str(deck.governing_deadline)
        if _unfired(deck, DeckNotice.KIND_SUSPENDED, 'suspended', period_key):
            due.append((DeckNotice.KIND_SUSPENDED, 'suspended', period_key))
    elif deck.auto_renews:
        # --- auto-renewing: ONE heads-up, not the expiry cadence -----------------
        # Nothing is expiring on this deck: the card is charged and the period
        # rolls forward, so the "renew or lose access" cadence was simply wrong
        # here (#2586). One notice per renewal, keyed to the date being renewed,
        # so next period's renewal gets its own.
        # The clock is paid_until, the date Stripe bills on, NOT the governing
        # deadline: a deck can carry a trial date that outlasts its paid period,
        # and the charge lands when the subscription bills (#2588 review find).
        # `auto_renews` guarantees paid_until is set and still ahead.
        days = (deck.paid_until - today).days
        if days <= RENEWAL_NOTICE_DAYS:
            period_key = str(deck.paid_until)
            if _unfired(deck, DeckNotice.KIND_RENEWAL, 'upcoming', period_key):
                due.append((DeckNotice.KIND_RENEWAL, 'upcoming', period_key))
    else:
        # --- expiry cadence (not for suspended decks; their deadline is history) --
        days = deck.days_until_expiry
        if days is not None and days <= EXPIRY_THRESHOLDS[-1][1]:
            # keyed to the GOVERNING deadline (the one days_until_expiry counts to
            # and the email reports), so a stale paid key can never suppress
            # reminders for a later governing trial date (#1734 B4)
            period_key = str(deck.governing_deadline)
            # the first (most specific) milestone whose window we're inside governs:
            # broader milestones are superseded, never fired late, and d1 ends the
            # cadence. Past the deadline `days` goes negative and d1 still matches, so
            # a deck that reaches us already inside its grace window gets that one
            # catch-up notice and then nothing: it is still fully usable in there, and
            # the suspension notice covers the day that stops being true (maintainer
            # decision, 2026-08-23). The guard above guarantees a window matches.
            threshold = [t for t, t_days in EXPIRY_THRESHOLDS if days <= t_days][0]
            if _unfired(deck, DeckNotice.KIND_EXPIRY, threshold, period_key):
                due.append((DeckNotice.KIND_EXPIRY, threshold, period_key))

    # --- current-student limit, once per level per semester ----------------------
    # not for suspended decks: students cannot sign in there at all, so a
    # "you are running out of student seats" nag is both wrong and unwelcome on a
    # deck whose owner may have walked away. Suspension closes the semester
    # (#1734 B2), which zeroes the count, but a suspended deck can still carry a
    # stale count above its cap, so this guard is explicit rather than relying on
    # the count being zero
    cap = deck.effective_max_active_users
    if cap > 0 and not deck.is_suspended:
        from courses.models import Semester

        level = _limit_level(deck.active_user_count, cap)  # cached count, refreshed moments earlier by the task
        # Keyed to the newest open semester (the manager lists newest term first), so
        # the levels re-arm when a semester starts and students join its courses
        # afresh. With no semester open nobody is current whatever the cached count
        # says, so there is nothing to warn about.
        semester = Semester.objects.open().first()
        if level and semester:
            period_key = f'semester-{semester.pk}'
            already_sent = DeckNotice.objects.filter(
                tenant=deck, kind=DeckNotice.KIND_LIMIT, period_key=period_key,
                threshold__in=LIMIT_LEVELS[LIMIT_LEVELS.index(level):],
            ).exists()
            if not already_sent:
                due.append((DeckNotice.KIND_LIMIT, level, period_key))

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


def _notification_detail(deck, kind):
    """The key fact for one notice's in-app notification, as a short sentence.

    The email tells the full story; the notification names the date or count the
    owner needs at a glance: the governing deadline (#1734 B4: the LATER of the
    trial and paid clocks, which drives all lifecycle wording), the grace end, or
    the seat usage. Assumes the notice is actually due, so the dates its branches
    read exist (e.g. a suspended deck always has a lapsed governing deadline).

    Args:
        deck (Tenant): The deck the notice is about.
        kind (str): The DeckNotice KIND_* being delivered.

    Returns:
        str: One sentence, ready to append after the notice's label.
    """
    clock = 'free trial' if deck.governing_clock_is_trial else 'subscription'
    deadline = date_format(deck.governing_deadline) if deck.governing_deadline else None
    if kind == DeckNotice.KIND_SUSPENDED:
        detail = f"this deck's {clock} ended on {deadline} and the grace period has run out"
        if deck.deletion_date:
            detail += f'; without a subscription the deck may be deleted after {date_format(deck.deletion_date)}'
        return detail + '.'
    if kind == DeckNotice.KIND_LIMIT:
        count, cap = deck.active_user_count, deck.effective_max_active_users
        if count >= cap:
            return f'{count} of {cap} current-student seats are used, so no more students can join a course.'
        left = cap - count
        return f"{count} of {cap} current-student seats are used, so {left} more student{'s' if left != 1 else ''} can join a course."
    if kind == DeckNotice.KIND_RENEWAL:
        # the billing date, not the governing deadline: those differ on a deck
        # whose trial date outlasts its paid period (#2588 review find)
        return f'this deck renews automatically on {date_format(deck.paid_until)}, with nothing for you to do.'
    # expiry cadence: approaching the deadline, or already inside the grace window
    days = deck.days_until_expiry
    if days is not None and days < 0:
        grace_end = date_format(deck.governing_deadline + timedelta(days=GRACE_PERIOD_DAYS))
        return f"this deck's {clock} ended on {deadline} and the grace period ends on {grace_end}."
    return f"this deck's {clock} ends on {deadline} ({days} day{'s' if days != 1 else ''} left)."


def _deliver(deck, kind):
    """Send one notice through both channels: owner email + in-app notification."""
    from tenant.tasks import send_email_message

    config = SiteConfig.get()
    days = deck.days_until_expiry
    # the deck's scheduled deletion day (Tenant.deletion_date: a year of
    # suspension, never counted from before the episode's first suspended
    # notice); the suspended email LEADS with it (maintainer request,
    # 2026-07-30: put the bottom line up front). The suspended notice's own
    # ledger row is written moments before delivery in the same transaction, so
    # the first send already reads its real warned-on day.
    suspended_since = deck.suspended_since
    deletion_date = deck.deletion_date
    context = {
        'deck': deck,
        'config': config,
        'days': days,
        'cap': deck.effective_max_active_users,
        # the trial/Maintenance student cap, for email copy that references it
        # (the deck's own `cap` can differ, e.g. a paid cap during grace)
        'trial_cap': TRIAL_MAX_ACTIVE_USERS,
        'count': deck.active_user_count,
        # how many more students can join a course before the cap stops them
        'seats_left': deck.effective_max_active_users - deck.active_user_count,
        # every date the owner could want (maintainer request, 2026-07-25): when the
        # paid period ended/ends, how long ago, when the grace window closes, and --
        # for suspended decks -- the day the suspension began. None when not applicable.
        'grace_days': GRACE_PERIOD_DAYS,
        # the unified grace window closes GRACE_PERIOD_DAYS after the deck's
        # governing (latest) deadline, trial and paid clocks alike (#1734 B4);
        # templates read the deadline and its origin from the deck itself
        # (governing_deadline / governing_clock_is_trial)
        'grace_end_date': (
            deck.governing_deadline + timedelta(days=GRACE_PERIOD_DAYS)
            if deck.governing_deadline else None
        ),
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
        DeckNotice.KIND_RENEWAL: ('renewal_reminder', 'subscription renewal reminder'),
        DeckNotice.KIND_LIMIT: ('limit_warning', 'current-student limit warning'),
        DeckNotice.KIND_SUSPENDED: ('suspended_notice', 'deck suspended warning'),
        DeckNotice.KIND_PAYMENT_FAILED: ('payment_failed', 'failed-payment warning'),
    }
    # what the renewal will actually charge, for the one email that has to state
    # it; cached per subscription by the billing helper, and None when Stripe
    # cannot say (the template then omits the plan line rather than guessing)
    if kind == DeckNotice.KIND_RENEWAL:
        from tenant.billing import subscription_plan_summary
        context['plan_summary'] = subscription_plan_summary(deck)
        # the renewal email counts to the BILLING date (paid_until), while `days`
        # above counts to the governing deadline: the two differ on a deck whose
        # trial date outlasts its paid period (#2588 review find)
        context['renewal_date'] = deck.paid_until
        context['renewal_days'] = (deck.paid_until - localdate()).days

    template_name, verb = templates[kind]
    if kind == DeckNotice.KIND_LIMIT and deck.active_user_count < deck.effective_max_active_users:
        # below the cap nothing is blocked yet, so the 90%, 95% and one-seat notices
        # are labelled as the heads-ups they are (#2824)
        verb = 'current-student limit heads-up'
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
        # the label plus the notice's key fact (deadline or seat count), then one
        # small "subscription details page" link: the bare "sent a reminder" line
        # told the owner nothing actionable (maintainer requests, 2026-08-08)
        verb=f'sent a {verb}: {_notification_detail(deck, kind)} See your',
        icon="<i class='fa fa-lg fa-fw fa-credit-card text-warning'></i>",
        url=reverse('decks:subscription'),
        link_text='subscription details page.',
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


def record_and_deliver_payment_failure(deck, invoice_id):
    """Record and deliver a payment-failure notice (Stripe webhook, plan §5.2 PR 7).

    Keyed by the failing invoice, so Stripe's own retries of the same invoice
    produce ONE notice, while next month's failing invoice produces a fresh one.
    No billing state changes -- the grace period already covers a failed renewal;
    this is purely the owner heads-up. Respects the same DECK_NOTICES_ENABLED
    report-only gate as the reminder engine. Must run inside the deck's tenant
    context (delivery resolves the owner and staff from the schema).

    Args:
        deck (Tenant): The deck whose renewal payment failed.
        invoice_id (str): The Stripe invoice id (in_...) that failed.

    Returns:
        str: A short summary string for the webhook log.
    """
    # a standing deletion request mutes this like every other lifecycle notice
    # (the webhook path doesn't go through evaluate_deck_notices, so the mute
    # has to be applied here too); the operator, not the owner, untangles any
    # still-live Stripe subscription when honoring the request
    if deck.deletion_requested_on is not None:
        return 'deletion requested: payment-failure notice muted'
    period_key = invoice_id[:32]  # ledger column width; ids are ~27 chars
    if not settings.DECK_NOTICES_ENABLED:
        return f"REPORT-ONLY (DECK_NOTICES_ENABLED off): would send [payment_failed/{period_key}]"
    with transaction.atomic():
        _, created = DeckNotice.objects.get_or_create(
            tenant=deck, kind=DeckNotice.KIND_PAYMENT_FAILED, threshold='invoice', period_key=period_key,
        )
        if not created:  # a Stripe retry of the same invoice; already notified
            return 'payment-failure notice already sent for this invoice'
        _deliver(deck, DeckNotice.KIND_PAYMENT_FAILED)
    return 'sent payment-failure notice'
