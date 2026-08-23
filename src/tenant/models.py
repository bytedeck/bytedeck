import re
from datetime import date

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.functions import Greatest
from django.utils.timezone import localdate, now, timedelta
from django.contrib.auth import get_user_model

from allauth.account.utils import user_email
from django_tenants.models import DomainMixin, TenantMixin

from hackerspace_online import settings

User = get_user_model()


def check_tenant_name(name):
    """ A tenant's name is used for both the schema_name and as the subdomain in the
    tenant's domain_url field, so {name} it must be valid for a schema and a url.
    """
    if not re.match(re.compile(r'^[a-z]'), name):
        raise ValidationError("The name must begin with a lower-case letter.")

    if re.search(re.compile(r'[A-Z]'), name):
        raise ValidationError("The name cannot contain capital letters.")

    if re.search(re.compile(r'-$'), name):
        raise ValidationError("The name cannot end in a dash.")

    if re.search(re.compile(r'--'), name):
        raise ValidationError("The name cannot have two consecutive dashes.")

    if not re.match(re.compile(r'^([a-z][a-z0-9]*(\-?[a-z0-9]+)*)$'), name):
        raise ValidationError("Invalid string used for the tenant name.")


# Length of every new deck's free trial: applied at deck creation through the
# trial_end_date field default, and quoted by the deck-request flow's copy.
TRIAL_LENGTH_DAYS = 60


def default_trial_end_date():
    return date.today() + timedelta(days=TRIAL_LENGTH_DAYS)


# The trial/Maintenance reference cap: the default for new (trial) decks, the cap
# the Maintenance tier's Stripe price carries in its metadata, and the number the
# status copy quotes. An admin-set `max_active_users` may differ and remains
# authoritative (see effective_max_active_users).
TRIAL_MAX_ACTIVE_USERS = 5

# Days of continued access after the deck's LATEST deadline (trial end or
# `paid_until`) before it counts as lapsed: every deck, trial or paid, falls back
# on the same grace window before suspension (#1734 B4: a trial is treated as
# just another kind of subscription). Codifies the 0-30-day "gold band" the
# tenant admin changelist has always shown for recently expired decks (#1494).
GRACE_PERIOD_DAYS = 30

# The status banner starts warning staff when the governing deadline (trial end or
# paid_until) is this many days away or closer (#1733's "2 week notice").
EXPIRY_WARNING_DAYS = 14

# A deck may be DELETED from the admin only after this long on the deletion
# clock (#2044 retirement policy): a year measured from the later of the
# suspension start and the episode's first suspended notice (see
# Tenant.deletion_date), so a deck is never deleted before it has had the full
# warned year to come back.
INACTIVE_DELETE_DAYS = 365


class Tenant(TenantMixin):
    # for reference: https://django-tenants.readthedocs.io/en/stable/use.html#deleting-a-tenant
    #
    # make sure it set to False (mandatory for ByteDeck project)
    auto_drop_schema = False
    """
    USE THIS WITH CAUTION!
    Set this flag to true on a parent class if you want the schema to be
    automatically deleted if the tenant row gets deleted.
    """

    # tenant = Tenant(domain_url='test.localhost', schema_name='test', name='Test')
    name = models.CharField(
        max_length=62,  # max length of a postgres schema name is 62
        unique=True,
        validators=[check_tenant_name],
        help_text="The name of your deck, for example the name `example` would give you the site: `example.bytedeck.com` \n\
        The name may only include lowercase letters, numbers, and dashes. \
        It must start with a letter, and may not end in a dash nor include consecutive dashes"
    )
    desc = models.TextField(blank=True)
    created_on = models.DateField(auto_now_add=True)
    max_active_users = models.SmallIntegerField(
        default=5,
        help_text="The maximum number of CURRENT students (registered in a course in the active semester) \
            on this deck; -1 = unlimited. Staff and merely-active (unregistered) students don't count."
    )
    trial_end_date = models.DateField(
        null=True,
        blank=True,  # clearing BOTH this and paid_until in the admin marks a deck comped/unmanaged (never suspended)
        default=default_trial_end_date,
        help_text="The date when the trial period ends. Blank or a date in the past means the deck is not in trial mode."
    )
    paid_until = models.DateField(
        blank=True, null=True,
        help_text="If the deck is not in trial mode, then the deck will become inaccessable to students after this date."
    )

    can_delete = models.BooleanField(
        default=False,
        # the #2044 retirement policy; the help text stays free of issue numbers
        # (they mean nothing to an admin reading the form)
        help_text="Arms this deck for deletion: deletion from the admin is refused until an "
                  "admin deliberately turns this on -- and even then only a suspended deck whose "
                  "owner has requested deletion, or one that has been suspended for over a year "
                  "(counted from when its owner was first sent the suspension notice), can "
                  "actually be deleted."
    )

    # An owner's standing request to have the deck deleted, made from the deck's
    # subscription page. Advisory: an operator still reviews it and arms
    # can_delete to honor it (the owner may not be a school deck's only
    # stakeholder), but it lets deletion skip the year-long suspension clock,
    # and it silences the deck's lifecycle reminder emails.
    deletion_requested_on = models.DateField(
        blank=True, null=True, editable=False,
        help_text="When the deck owner asked for this deck to be deleted; blank = no standing request. "
                  "Set and cleared by the owner from the deck's subscription page."
    )
    deletion_requested_by = models.CharField(
        max_length=255, blank=True, default='', editable=False,
        help_text="Who asked (their username at the time of the request), for the audit trail."
    )

    # Stripe linkage (epic #1729 PR 6). Blank on decks whose subscriptions are managed
    # manually; set automatically by checkout reconciliation, or by hand in the admin
    # when backfilling legacy subscribers (#2043).
    stripe_customer_id = models.CharField(
        max_length=255, blank=True, default='', db_index=True,
        help_text="The Stripe Customer id (cus_...) this deck bills to. Blank = not linked to Stripe."
    )
    stripe_subscription_id = models.CharField(
        max_length=255, blank=True, default='',
        help_text="The Stripe Subscription id (sub_...) paying for this deck. Blank = no Stripe subscription."
    )
    stripe_auto_renews = models.BooleanField(
        default=False, editable=False,
        help_text="Whether Stripe says the linked subscription bills again on its own. Cleared when the "
                  "owner sets it to cancel at period end, when a renewal starts failing, and on decks "
                  "with no Stripe subscription. Synced from Stripe, never edited here."
    )
    stripe_portal_configuration_id = models.CharField(
        max_length=255, blank=True, default='',
        help_text="The Billing Portal configuration (bpc_...) whose headline names this deck, created "
                  "automatically on the owner's first portal visit. Clear it to have the next portal visit "
                  "rebuild the configuration from the account default (e.g. after changing the default's "
                  "features in the Stripe dashboard)."
    )

    # These are calculated / cached fields that are needed so they can be filterable/sortable in Django Admin
    # normal annotation to the Django Admin queryset doesn't work because these fields aren't linked via foreign keys
    # instead they have to be found within the tenant's context / schema
    owner_full_name_cached = models.CharField(
        max_length=255, blank=True, null=True, editable=False,
        help_text="This is a cached field: the full name of the Deck Owner (set in each deck's Site Config) will be used."
    )
    owner_email_cached = models.EmailField(
        null=True, blank=True, editable=False,
        help_text="This is a cached field: the verified email address of the Deck Owner (set in each deck's Site Config) will be used."
    )

    active_user_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="This is a cached field: the number of CURRENT students (registered in a course in the \
            active semester). Staff and superusers don't count."
    )

    total_user_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="This is a cached field: all users, including currently unregistered and archived users."
    )

    quest_count = models.PositiveSmallIntegerField(
        default=0,
        help_text="This is a cached field: the number of quests currently available on the deck "
                  "(published, past their start date, not expired, not archived, and in an active "
                  "campaign or no campaign)"
    )

    last_staff_login = models.DateTimeField(
        blank=True, null=True,
        help_text="This is a cached field: the last time a staff user logged in to the deck."
    )

    google_signon_enabled = models.BooleanField(
        default=False,
        help_text="This is a cached field: Whether Google signon has been enabled for this deck."
    )

    cached_fields_updated_on = models.DateTimeField(
        blank=True, null=True, editable=False,
        help_text="When the cached fields above were last refreshed (nightly via the deck status check task)."
    )
    # END CALCULATED / CACHED FIELDS ##################################

    def __str__(self):
        return f'{self.schema_name} - {self.primary_domain_url}'

    def save(self, *args, **kwargs):
        from tenant.utils import generate_schema_name
        if not self.schema_name:
            self.schema_name = generate_schema_name(self.name)

        super().save(*args, **kwargs)

    # BILLING / LIFECYCLE STATUS ######################################
    # Derived from trial_end_date and paid_until rather than stored, so status can
    # never drift from the dates admins see and edit. Groundwork for epic #1729.

    @property
    def subscription_active(self):
        """Whether the deck currently has paid access: `paid_until` is set and today
        is on or before it plus the grace period.

        "Today" is computed with timezone.localdate() (settings.TIME_ZONE), matching
        the {% now %} date the admin changelist compares against -- date.today() would
        use the container's OS clock (typically UTC) and flip state hours early.
        """
        return self.paid_until is not None and localdate() <= self.paid_until + timedelta(days=GRACE_PERIOD_DAYS)

    @property
    def governing_deadline(self):
        """The single deadline the deck's lifecycle runs on: the LATEST of its set
        clocks (trial end and/or `paid_until`), or None for a comped/managed-manually
        deck with both dates blank. Expiry, the unified grace window, and suspension
        are all measured from this one date (#1734 B4: a trial is just another kind
        of subscription)."""
        clocks = [d for d in (self.trial_end_date, self.paid_until) if d is not None]
        return max(clocks) if clocks else None

    @property
    def governing_clock_is_trial(self):
        """Whether the governing deadline comes from the TRIAL clock, so status
        copy should say "trial ended" rather than "subscription expired". False
        when the paid clock governs, when the dates tie (subscription language
        wins), and when the deck has no dates at all. Presentation must key off
        this rather than `paid_until` existing: trial_end_date is never cleared,
        and an admin can extend a trial past an old lapsed paid date, making the
        trial the clock the lifecycle actually runs on."""
        return (
            self.trial_end_date is not None
            and (self.paid_until is None or self.trial_end_date > self.paid_until)
        )

    @property
    def in_grace_period(self):
        """Whether the deck is past its governing deadline but still within the
        unified grace window (access retained, expiry warnings due). Trial and
        paid clocks get the same grace (#1734 B4)."""
        deadline = self.governing_deadline
        if deadline is None:
            return False
        return deadline < localdate() <= deadline + timedelta(days=GRACE_PERIOD_DAYS)

    @property
    def grace_days_remaining(self):
        """Days of grace left after the latest deadline; None when not in the grace
        period. 0 on the final day (the grace period ends today). Drives the
        expired banner's "grace period ends in N days" copy.

        days_until_expiry is negative throughout the grace window, so the days
        left until suspension are GRACE_PERIOD_DAYS + days_until_expiry.
        """
        if not self.in_grace_period:
            return None
        return GRACE_PERIOD_DAYS + self.days_until_expiry

    @property
    def is_on_trial(self):
        """Whether the deck is in trial mode: no active subscription, and a trial
        clock that hasn't run out."""
        return (
            not self.subscription_active
            and self.trial_end_date is not None
            and localdate() <= self.trial_end_date
        )

    @property
    def is_suspended(self):
        """Whether every clock this deck was ever given (trial and/or paid) has
        lapsed AND the unified grace window after the LATEST one has closed: every
        deck, trial or paid, keeps access for GRACE_PERIOD_DAYS past its latest
        deadline before suspension (#1734 B4: a trial is treated as just another
        kind of subscription, with a single latest-clock deadline).

        A deck with BOTH dates blank is never suspended: that is the escape hatch for
        comped/legacy decks managed outside the subscription lifecycle, reached by
        clearing both date fields on the deck in the public-tenant admin.
        """
        deadline = self.governing_deadline
        if deadline is None:
            return False
        return localdate() > deadline + timedelta(days=GRACE_PERIOD_DAYS)

    @property
    def effective_max_active_users(self):
        """The current-student cap that should be enforced right now: ALWAYS the
        admin-set ``max_active_users`` (-1 = unlimited).

        Suspension does not affect the cap: a suspended deck is closed to
        everyone but its owner and the ByteDeck support admin (see
        ``tenant.middleware.OwnerOnlyWhenSuspendedMiddleware``). The
        trial-level cap belongs to the Maintenance tier, whose Stripe price
        metadata writes it here. Whatever the admin sets, higher or lower,
        always wins (comps and special cases; maintainer decision on #2178).
        """
        return self.max_active_users

    @property
    def is_on_maintenance(self):
        """Whether the deck's active subscription is a MAINTENANCE subscription:
        paid -- so the deck never suspends, and can never time out for deletion
        (deletion requires suspension, #2044) -- but with the cap left at (or
        below) the trial student limit.

        The low-cost maintenance tier is simply a Stripe price whose metadata
        cap IS the trial cap, so this is derived rather than stored: any active
        subscription that doesn't lift the cap above trial limits is, by
        definition, maintenance. Unlimited (-1) decks are never maintenance.
        """
        return (
            self.subscription_active
            and self.max_active_users != -1
            and self.max_active_users <= TRIAL_MAX_ACTIVE_USERS
        )

    # one human label per subscription_status slug; the subscription page's badge
    # and the tenant admin's Subscription column both render from this map, so
    # the same state always shows the same word everywhere. The KEY ORDER is
    # meaningful: it is the branch order of the subscription_status chain below,
    # and doubles as the sort rank annotate_subscription_status() applies, so
    # sorting the admin's Subscription column ascending lists the decks that
    # need attention (suspended, then grace) before the settled ones.
    SUBSCRIPTION_STATUS_LABELS = {
        'suspended': 'Suspended',
        'grace': 'Grace period',
        'trial': 'Free trial',
        'maintenance': 'Maintenance',
        'subscribed': 'Subscribed',
        'manual': 'Managed manually',
    }

    @property
    def subscription_status(self):
        """The deck's lifecycle status as a slug: the single precedence chain
        behind every status display (the subscription page's badge and the
        tenant admin's Subscription column), so the two can never disagree.

        Precedence matters: a deck past its grace window is 'suspended' even
        though its trial dates still exist, and a deck in the paid clock's
        grace window is 'grace' even though ``subscription_active`` is still
        True there (access is retained through grace). The LATEST clock governs
        the lifecycle (#1734 B4), so when the trial clock governs (and hasn't
        lapsed into the branches above) the deck is 'trial' even if an older
        ``paid_until`` still keeps ``subscription_active`` True through its
        grace tail. 'manual' is the both-dates-blank escape hatch for
        comped/legacy decks managed outside the subscription lifecycle.

        Returns:
            str: One of the ``SUBSCRIPTION_STATUS_LABELS`` keys: 'suspended',
            'grace', 'maintenance', 'subscribed', 'trial' or 'manual'.
        """
        if self.is_suspended:
            return 'suspended'
        if self.in_grace_period:
            return 'grace'
        if self.governing_clock_is_trial:
            # not suspended and not in grace, so the governing trial clock is
            # still running: the deck is on trial regardless of any older,
            # still-in-grace paid_until (which would misreport as subscribed)
            return 'trial'
        if self.is_on_maintenance:
            return 'maintenance'
        if self.subscription_active:
            return 'subscribed'
        return 'manual'

    @classmethod
    def annotate_subscription_status(cls, queryset):
        """Annotate `subscription_status_rank`: the subscription_status precedence
        chain, expressed in SQL so a list view can SORT on the status.

        `subscription_status` is derived in Python, and a column of derived values
        has nothing for the database to order by, which is why the tenant admin's
        Subscription column needs this to be sortable at all.

        Each `When` mirrors the property of the same name, and the rank is the
        slug's position in SUBSCRIPTION_STATUS_LABELS, so ascending lists suspended
        decks first and managed-manually ones last. The two implementations must
        agree: `test_annotate_subscription_status__matches_the_python_chain` builds
        a deck in every status and asserts the annotation reproduces the property
        exactly, so changing one without the other fails the suite.

        Args:
            queryset (QuerySet): Any Tenant queryset.

        Returns:
            QuerySet: The same queryset with `governing_deadline_date` and
            `subscription_status_rank` annotated. The deadline alias deliberately
            differs from the `governing_deadline` property so it doesn't shadow it
            on the returned instances.
        """
        today = localdate()
        # the day a deck's grace window closes: a governing deadline older than
        # this is suspended, one on or after it is still inside grace
        grace_cutoff = today - timedelta(days=GRACE_PERIOD_DAYS)
        rank = {slug: position for position, slug in enumerate(cls.SUBSCRIPTION_STATUS_LABELS)}
        # subscription_active: a paid clock whose grace tail has not run out
        paid_access = models.Q(paid_until__isnull=False, paid_until__gte=grace_cutoff)
        return queryset.annotate(
            # Postgres GREATEST skips NULLs, so this is governing_deadline: the
            # later of the two clocks, and NULL only when neither is set (a NULL
            # then fails every date comparison below and falls through to 'manual')
            governing_deadline_date=Greatest('trial_end_date', 'paid_until'),
        ).annotate(
            subscription_status_rank=models.Case(
                models.When(governing_deadline_date__lt=grace_cutoff, then=models.Value(rank['suspended'])),
                # past the deadline; anything that also outlived the grace
                # window was already claimed by the branch above
                models.When(governing_deadline_date__lt=today, then=models.Value(rank['grace'])),
                models.When(
                    models.Q(trial_end_date__isnull=False)
                    & (models.Q(paid_until__isnull=True) | models.Q(trial_end_date__gt=models.F('paid_until'))),
                    then=models.Value(rank['trial']),
                ),
                models.When(
                    paid_access & ~models.Q(max_active_users=-1) & models.Q(max_active_users__lte=TRIAL_MAX_ACTIVE_USERS),
                    then=models.Value(rank['maintenance']),
                ),
                models.When(paid_access, then=models.Value(rank['subscribed'])),
                default=models.Value(rank['manual']),
                output_field=models.IntegerField(),
            ),
        )

    @property
    def subscription_status_label(self):
        """The human-readable label for ``subscription_status``, e.g. 'Free trial'.

        Returns:
            str: The ``SUBSCRIPTION_STATUS_LABELS`` entry for the current status.
        """
        return self.SUBSCRIPTION_STATUS_LABELS[self.subscription_status]

    @property
    def days_until_expiry(self):
        """Days until the deck's governing deadline: the LATEST of its set clocks
        (trial end and/or `paid_until`), the single deadline the unified grace
        window and suspension are measured from (#1734 B4).

        The latest-clock rule matters because trial_end_date is set at creation and
        never cleared when a deck subscribes: a lapsed subscriber should read as
        "expired N days ago" relative to its recent paid_until, not its ancient trial
        date. Negative once the deadline has passed (the reminder cadence keeps firing
        through the grace window); None when the deck has no dates at all
        (comped/legacy decks).
        """
        deadline = self.governing_deadline
        if deadline is None:
            return None
        return (deadline - localdate()).days

    @property
    def is_over_user_limit(self):
        """Whether the deck's LIVE current-student count exceeds its effective cap.

        Recounts live (like the registration choke points) rather than reading the
        nightly-cached ``active_user_count``: the banner this drives renders next
        to pages that list current students live, so a stale cached count reads as
        a bug (production find: banner claimed 0 seats used beside a student list
        showing 1). Only the banner uses this property, and only for staff, so the
        extra COUNT per staff page load is acceptable. Always False for unlimited
        (-1) decks. Must be evaluated inside the deck's schema.
        """
        if self.effective_max_active_users == -1:
            return False
        return self.get_active_user_count() > self.effective_max_active_users

    @property
    def auto_renews(self):
        """Whether this deck's paid access renews on its own, so every lifecycle
        surface should say "renews" rather than "expires" (#2586).

        ``stripe_auto_renews`` is what Stripe last told us; this adds the sanity
        check that the deadline has not already passed. A renewal that never
        landed (a payment failing while its webhook is late, or a webhook
        outage) would otherwise leave the flag set on a deck whose paid period
        is history, and that deck really is expiring: it falls back to the
        expiry cadence, the grace-window banner, and eventually suspension
        rather than sitting reassured and silent.
        """
        days = self.days_until_expiry
        return self.stripe_auto_renews and days is not None and days >= 0

    @property
    def is_expiring_soon(self):
        """Whether the governing deadline is within EXPIRY_WARNING_DAYS (or already
        past, while still in the paid grace window) -- i.e. the status banner should
        escalate from "info" to "warning".

        False for suspended decks (they get the suspension banner instead), for
        auto-renewing decks (nothing is expiring: the card is charged and the
        period rolls forward, #2586), and for unmanaged/comped decks (no
        deadline at all).
        """
        if self.is_suspended or self.auto_renews:
            return False
        days = self.days_until_expiry
        return days is not None and days <= EXPIRY_WARNING_DAYS

    @property
    def suspended_since(self):
        """The first day of the current suspension episode: the day after the deck's
        LAST covered day. A trial and a paid period alike cover through their
        deadline plus the unified grace window (#1734 B4), so this is the day
        after the latest clock's grace closes. None while the deck is not
        suspended. is_suspended requires at least one date field, so a suspended
        deck always has at least one covered day to count from.
        """
        if not self.is_suspended:
            return None
        return self.governing_deadline + timedelta(days=GRACE_PERIOD_DAYS + 1)

    @property
    def deletion_date(self):
        """The day this deck becomes eligible for deletion under the retirement
        policy (#2044): INACTIVE_DELETE_DAYS after the deletion clock starts. None
        while the deck is not suspended.

        The clock starts at the LATER of the suspension itself and the day the deck
        was first WARNED (the suspension episode's 'suspended' DeckNotice ledger
        row): a legacy deck whose dates lapsed long before the notice machinery
        went live gets its full year measured from its first suspended notice,
        never from a backdated lapse (maintainer decision, 2026-07-31). A deck
        never warned at all reads as warned today, so its clock has not started.

        Must be read on a saved Tenant row (the ledger lookup filters on this
        instance); the early Nones for non-suspended decks need no lookup.
        """
        since = self.suspended_since
        if since is None:
            return None
        # the episode key mirrors the suspended notice's period_key (the lapsed
        # governing deadline), so this finds exactly this episode's first warning
        first_warned_row = DeckNotice.objects.filter(
            tenant=self, kind=DeckNotice.KIND_SUSPENDED, threshold='suspended',
            period_key=str(self.governing_deadline),
        ).order_by('sent_on').first()
        warned_on = first_warned_row.sent_on if first_warned_row else localdate()
        return max(since, warned_on) + timedelta(days=INACTIVE_DELETE_DAYS)

    @property
    def is_deletable(self):
        """Whether the admin may delete this deck (and drop its schema) -- the
        #2044 retirement policy. ALL of these must hold:

        * ``can_delete`` was deliberately armed by an admin (default False);
        * the deck's waiting is over (``deletion_eligibility``): it is SUSPENDED
          and either its owner has a standing deletion request or its
          ``deletion_date`` has arrived (a year of suspension, measured from the
          later of the suspension start and the episode's first suspended
          notice, so unrequested deletion can never outrun the year the warning
          email promised; a deck never warned at all never times out, since its
          clock has not started). The public schema is never eligible.
        """
        return self.can_delete and self.deletion_eligibility is not None

    @property
    def deletion_eligibility(self):
        """Why this deck's deletion waiting is over: ``'request'`` (its owner has a
        standing deletion request, which outranks the year clock), ``'timeout'``
        (the year-long suspension clock has run out), or None while neither
        holds. Only a SUSPENDED deck is ever eligible (an active subscription, a
        running trial, or a managed-manually deck is not, and the operator can
        suspend a live deck by editing its dates), and the public schema never is.

        Arming ``can_delete`` is the operator's remaining step: ``is_deletable``
        is exactly this eligibility plus that arming, and the tenant admin's
        "deletable" column shows this value so decks whose waiting is over
        surface before anyone opens their change form.

        Returns:
            str | None: ``'request'``, ``'timeout'``, or None.
        """
        from django_tenants.utils import get_public_schema_name

        if self.schema_name == get_public_schema_name():
            return None
        if not self.is_suspended:  # active sub, on trial, or managed manually
            return None
        if self.deletion_requested_on is not None:
            return 'request'
        if localdate() >= self.deletion_date:
            return 'timeout'
        return None

    def sync_from_stripe_subscription(self, subscription):
        """The SINGLE write path from a Stripe Subscription object to this deck (plan §5.2).

        Every webhook handler, the admin "Sync from Stripe" action, and the
        nightly reconcile funnel through here -- handlers never write billing
        fields directly. All guards are evaluated against the row's FRESH state
        under ``select_for_update()`` (this instance may have been loaded before
        a concurrent sync), then applied as a targeted ``QuerySet.update()`` --
        which bypasses ``save()`` hooks and model validation -- plus cache
        invalidation. Events for a subscription OTHER than the deck's currently
        linked one are ignored outright: webhook resolution can fall back to the
        customer id, so a delayed event for a superseded subscription could
        otherwise unlink or relink the wrong one (legitimate link switches go
        through the checkout reconciler or the admin, which change the linked id
        itself). Applies:

        * ``paid_until`` = the subscription's current period end -- **monotonic**
          (a re-delivered or out-of-order older event can never LOWER it) and
          **only while the subscription is active/trialing**: an incomplete
          first payment or a past_due renewal never extends access (Stripe rolls
          the period forward at renewal even while payment is failing; the grace
          period covers that window). A canceled subscription keeps its
          paid_until (the deck is paid through the period end).
        * ``max_active_users`` from the Price's ``metadata.max_active_users``
          (dashboard-editable tiers), falling back to
          ``settings.STRIPE_PRICE_TIER_MAP[price_id]`` -- likewise only while
          active/trialing; untouched when neither source is set.
        * ``stripe_subscription_id`` linked while the subscription lives, and
          cleared when it is canceled/expired (the customer link is kept for
          the billing portal and future checkouts).

        Args:
            subscription (dict): A Stripe Subscription object (or test double).

        Returns:
            str: A short human-readable summary of what changed, for logs.
        """
        from tenant.billing import (
            clear_plan_summary_cache, subscription_auto_renews, subscription_max_active_users,
            subscription_period_end_date,
        )
        from tenant.utils import invalidate_current_deck_cache

        status = subscription.get('status')
        # Only a PAID subscription grants anything: an 'incomplete' first payment
        # (failed 3DS) must not grant a paid period, and a 'past_due' renewal must
        # not either -- Stripe rolls current_period_end forward at renewal even
        # while the payment is still failing, and the grace period exists exactly
        # to cover that window. paid_until therefore only advances on
        # active/trialing (i.e. on payment), matching the checkout reconciler.
        grants_access = status in ('active', 'trialing')
        sub_id = subscription.get('id') or ''

        with transaction.atomic():
            # Lock the row and evaluate every guard against its FRESH state: this
            # instance can be stale (loaded before a concurrent sync committed),
            # and deciding from stale state would let an out-of-order event lower
            # paid_until past the monotonic guard.
            current = Tenant.objects.select_for_update().get(pk=self.pk)

            # Identity guard: only the deck's linked subscription may change its
            # billing state. A delayed event for a superseded subscription reaches
            # this deck via the customer-id fallback and must not unlink or relink
            # anything. An unlinked deck accepts any subscription (initial link).
            if current.stripe_subscription_id and sub_id and sub_id != current.stripe_subscription_id:
                return f"ignored: {sub_id} is not this deck's linked subscription"

            updates = {}
            if grants_access:
                period_end = subscription_period_end_date(subscription)
                if period_end is not None and (current.paid_until is None or period_end > current.paid_until):
                    updates['paid_until'] = period_end

                cap = subscription_max_active_users(subscription)
                if cap is not None and cap != current.max_active_users:
                    updates['max_active_users'] = cap

            # tracked on every sync, not just while granting access: a renewal
            # that starts failing (past_due) or an owner's "cancel at period end"
            # must both put the deck back on the expiry cadence (#2586)
            auto_renews = subscription_auto_renews(subscription)
            if auto_renews != current.stripe_auto_renews:
                updates['stripe_auto_renews'] = auto_renews

            if status in ('canceled', 'incomplete_expired'):
                # unlink strictly on an id match: with the identity guard above this
                # means the event's own sub, and a malformed id-less payload (which
                # the guard cannot see) unlinks nothing (review find on #2110)
                if current.stripe_subscription_id and sub_id == current.stripe_subscription_id:
                    updates['stripe_subscription_id'] = ''
            elif sub_id and sub_id != current.stripe_subscription_id:
                updates['stripe_subscription_id'] = sub_id

            if updates:
                Tenant.objects.filter(pk=self.pk).update(**updates)

        # The subscription page's cached plan summary can go stale even when no
        # Tenant field changes (a portal plan switch can keep the period end and
        # cap while changing the product/price on display), so it is cleared on
        # every sync, for the event's subscription and the previously linked one.
        clear_plan_summary_cache(self.schema_name, sub_id, current.stripe_subscription_id)

        if updates:
            for field, value in updates.items():
                setattr(self, field, value)
            # invalidate after the write is committed/queued, so a concurrent
            # request can't re-cache the pre-update row between the two steps
            invalidate_current_deck_cache(self.schema_name)
            return 'updated ' + ', '.join(f'{field}={value}' for field, value in updates.items())
        return 'no changes'

    # END BILLING / LIFECYCLE STATUS ##################################

    def update_cached_fields(self):
        """
        Updates the cached fields for the tenant so Django Admin displays the latest values.

        Saves with update_fields so this instance (often loaded well before the save,
        e.g. in an admin queryset loop) can't clobber a concurrent edit to any other
        column, such as an admin adjusting paid_until.
        """
        self.owner_full_name_cached = self.get_owner_full_name_cached()
        self.owner_email_cached = self.get_owner_email_cached()
        self.active_user_count = self.get_active_user_count()
        self.total_user_count = self.get_total_user_count()
        self.quest_count = self.get_quest_count()
        self.last_staff_login = self.get_last_staff_login()
        self.google_signon_enabled = self.get_google_signon_enabled()
        self.cached_fields_updated_on = now()
        self.save(update_fields=[
            'owner_full_name_cached',
            'owner_email_cached',
            'active_user_count',
            'total_user_count',
            'quest_count',
            'last_staff_login',
            'google_signon_enabled',
            'cached_fields_updated_on',
        ])

    def get_owner_full_name_cached(self):
        """
        Returns full name (or username) from SiteConfig().deck_owner object.
        """
        SiteConfig = apps.get_model('siteconfig', 'SiteConfig')
        owner = SiteConfig.get().deck_owner

        # get the full name of the user, or if none is supplied will return the username
        return owner.get_full_name() or owner.username

    def get_owner_email_cached(self):
        """
        Returns the deck owner's email address (SiteConfig().deck_owner) in
        allauth's canonical lowercase form (``user_email`` lowercases, matching
        how ``EmailAddress`` rows are stored), or None when the owner has no
        email set.

        The owner's plain ``User.email`` is the operational contact address for
        the deck: notice emails, checkout prefill, and the Stripe backfill
        report's matching all ride on it. It is deliberately NOT gated on allauth
        ``EmailAddress`` bookkeeping: owners of decks created before the current
        sign-up flow often have a ``User.email`` but no ``EmailAddress`` row at
        all, and requiring one silently disabled every owner email for exactly
        the legacy decks that most need warning (maintainer decision,
        2026-08-01; the ``backfill_owner_emails`` command normalizes the missing
        rows so legacy owners match what deck creation sets up today).
        """
        SiteConfig = apps.get_model('siteconfig', 'SiteConfig')
        owner = SiteConfig.get().deck_owner
        return user_email(owner) or None

    def get_google_signon_enabled(self):
        """
        Returns whether Google signon has been enabled for this tenant by accessing the tenant's SiteConfig option
        """
        SiteConfig = apps.get_model('siteconfig', 'SiteConfig')
        site_config = SiteConfig.get()
        return site_config.enable_google_signin

    def get_total_user_count(self):
        """
        Returns the total number of users, including unregistered and archived users.
        """
        return User.objects.count()

    def get_active_user_count(self):
        """
        Returns the number of CURRENT students: those registered in a course in the
        active semester. (The method name keeps the legacy field naming; "current"
        is the deck vocabulary -- merely-active students who aren't registered this
        semester don't count.)

        Staff and superusers never count -- pricing tiers are based on current
        students only (maintainer decision, PR #2047 / epic #1729).
        students_only=True already restricts the enrolled set to non-staff,
        non-test-account users, and the queryset it returns is limited to
        is_active=True (so archived/inactive students stop counting, #1733);
        superusers are excluded explicitly since a superuser isn't necessarily
        staff.

        active_only=True further excludes registrations deactivated by a semester
        close (e.g. the suspension auto-close, #1734 redesign B2), so a closed
        semester contributes zero current students.

        The count spans every semester that is open, so a deck running two cohorts on
        different calendars pays for both (issue #2157 Phase 3).

        Returns:
            int: how many distinct current students the deck has.
        """
        CourseStudent = apps.get_model('courses', 'CourseStudent')
        return (
            CourseStudent.objects.all_users_in_open_semesters(students_only=True, active_only=True)
            .exclude(is_superuser=True)
            .count()
        )

    def get_quest_count(self):
        """The number of quests currently AVAILABLE on the deck: published, past
        their start date, not expired, not archived, and in an active campaign
        (or no campaign). This is the pool the students' Available quests tab
        draws from, before per-student filtering (prerequisites, submissions),
        so the deck stat matches what the deck actually offers rather than
        counting drafts and expired quests.
        """
        Quest = apps.get_model('quest_manager', 'Quest')
        return Quest.objects.get_active().count()

    def get_last_staff_login(self):
        """
        Returns the last time a staff member loggin in to the tenant. Excludes teh deck admin account which is owned by ByteDeck
        """
        staff = User.objects.filter(last_login__isnull=False).filter(is_staff=True).exclude(username=settings.TENANT_DEFAULT_ADMIN_USERNAME)
        last_staff_logged_in = staff.order_by('-last_login').first()

        if last_staff_logged_in:
            return last_staff_logged_in.last_login

        return None

    @property
    def primary_domain_url(self):
        return self.get_primary_domain().domain

    def get_root_url(self):
        """
        Returns the root url of the tenant in the form of:
        scheme://[subdomain.]domain[.topleveldomain][:port]

        Port 8000 is hard coded for development

        Examples:
        - "hackerspace.bytedeck.com"
        - "hackerspace.localhost:8000"
        """

        domain_url = self.get_primary_domain().domain
        if 'localhost' in domain_url:  # Development
            return f"http://{domain_url}:8000"
        else:  # Production
            return f"https://{domain_url}"

    @classmethod
    def get(cls):
        """ Used to access the Tenant object for the current connection """
        from django.db import connection
        return Tenant.objects.get(schema_name=connection.schema_name)


class DeckNotice(models.Model):
    """Idempotence/audit ledger for deck status notices (epic #1729 PR 5): one row
    per notice actually sent.

    The unique constraint makes every send exactly-once and the cadence
    self-re-arming: `period_key` carries the deadline (or month) the notice was
    about, so when a renewal advances `paid_until` (or a new month starts, for
    limit warnings) the same threshold becomes sendable again with no bespoke
    reset logic. Date-based predicates plus this ledger also make multi-day beat
    outages catch-up-safe: late, never duplicated.
    """
    KIND_EXPIRY = 'expiry'
    KIND_RENEWAL = 'renewal'
    KIND_LIMIT = 'limit'
    KIND_SUSPENDED = 'suspended'
    KIND_PAYMENT_FAILED = 'payment_failed'  # reserved for the Stripe webhook phase (plan PR 7)
    KIND_CHOICES = [
        (KIND_EXPIRY, 'Trial/subscription expiry reminder'),
        (KIND_RENEWAL, 'Subscription auto-renewal reminder'),
        (KIND_LIMIT, 'Current-student limit warning'),
        (KIND_SUSPENDED, 'Deck suspended'),
        (KIND_PAYMENT_FAILED, 'Payment failed'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='notices')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    threshold = models.CharField(
        max_length=20,
        help_text="Which step of the cadence fired: 'd30'/'d14'/'d7'/'d1', 'upcoming', 'pct80'/'pct100', 'suspended', or 'invoice'."
    )
    period_key = models.CharField(
        max_length=32,
        help_text="The deadline (expiry/suspension) or month (limit warnings) this notice was about; \
            a new value re-arms the threshold."
    )
    sent_on = models.DateField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['tenant', 'kind', 'threshold', 'period_key'], name='unique_deck_notice'),
        ]

    def __str__(self):
        """Audit identifier: the deck's schema name, kind/threshold, and period key."""
        return f'{self.tenant.schema_name}: {self.kind}/{self.threshold} for {self.period_key}'


class TenantDomain(DomainMixin):
    pass


class ReleaseNotification(models.Model):
    """Public-schema record of a ByteDeck release version that deck staff have been
    notified about, so ``tenant.tasks.poll_release_announcement`` notifies each
    version exactly once across every deck.

    ``notified=False`` marks a baseline row written the first time the poll runs:
    the version that shipped before this feature was enabled is recorded but no
    notification is sent, so turning the feature on never mass-notifies staff about
    a release they already have. Lives in the public schema (tenant app), like the
    Tenant registry itself, because "which versions have been announced" is one
    global fact, not a per-deck one.
    """
    version = models.CharField(max_length=20, unique=True)
    discussion_url = models.CharField(max_length=500, blank=True, default="")
    notified = models.BooleanField(
        default=True,
        help_text="False for the baseline row recorded on the first poll (no notification sent).",
    )
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Audit identifier: the version and whether staff were actually notified."""
        return f"{self.version} ({'notified' if self.notified else 'baseline'})"


class StripeEventLog(models.Model):
    """Idempotence and audit log for received Stripe webhook events (plan §5.2).

    ``event_id`` is unique, so a duplicate webhook delivery fails get_or_create
    and returns 200 before any handler runs. Rows double as an audit trail for
    the repo's only csrf_exempt endpoint. Lives in the public schema (tenant
    app), like the Tenant registry itself.
    """
    event_id = models.CharField(max_length=255, unique=True)
    event_type = models.CharField(max_length=100)
    schema_name = models.CharField(
        max_length=63, blank=True, default='',
        help_text="The deck this event was resolved to, when it could be resolved."
    )
    received_on = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        """Audit identifier: the Stripe event id, its type, and the resolved deck."""
        return f'{self.event_id} ({self.event_type}) -> {self.schema_name or "unresolved"}'
