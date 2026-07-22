import re
from datetime import date

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.timezone import localdate, now, timedelta
from django.contrib.auth import get_user_model

from allauth.account.utils import user_email
from allauth.account.models import EmailAddress
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


def default_trial_end_date():
    return date.today() + timedelta(days=60)


# Trial decks -- and suspended decks, which revert to trial limits (#1734) -- are
# capped at this many active users.
TRIAL_MAX_ACTIVE_USERS = 5

# Days of continued paid access after `paid_until` before a deck counts as lapsed.
# Codifies the 0-30-day "gold band" the tenant admin changelist has always shown
# for recently expired decks (#1494).
GRACE_PERIOD_DAYS = 30

# The status banner starts warning staff when the governing deadline (trial end or
# paid_until) is this many days away or closer (#1733's "2 week notice").
EXPIRY_WARNING_DAYS = 14


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
    owner_full_name = models.CharField(
        max_length=255, blank=True, null=True,
        help_text="DEPRECATED: the full name of the Deck Owner (set in each deck's Site Config) will be used. \
        This field will be removed in a future update",
    )
    owner_email = models.EmailField(
        null=True, blank=True,
        help_text="DEPRECATED: the verified email address of the Deck Owner (set in each deck's Site Config) will be used. \
        This field will be removed in a future update",
    )
    max_active_users = models.SmallIntegerField(
        default=5,
        help_text="The maximum number of CURRENT students (registered in a course in the active semester) \
            on this deck; -1 = unlimited. Staff and merely-active (unregistered) students don't count."
    )
    max_quests = models.SmallIntegerField(
        default=100,
        help_text="The maximum number of quests that can be active on this deck (archived quests are considered inactive); -1 = unlimited."
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
        help_text="This is a cached field: the number of non-archived quests in the deck"
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
    def in_grace_period(self):
        """Whether the deck is past `paid_until` but still within the grace period
        (access retained, expiry warnings due)."""
        return self.subscription_active and localdate() > self.paid_until

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
        """Whether every clock this deck was ever given (trial and/or paid) has lapsed.

        A deck with BOTH dates blank is never suspended: that is the escape hatch for
        comped/legacy decks managed outside the subscription lifecycle, reached by
        clearing both date fields on the deck in the public-tenant admin.
        """
        if self.subscription_active or self.is_on_trial:
            return False
        return self.paid_until is not None or self.trial_end_date is not None

    @property
    def effective_max_active_users(self):
        """The current-student cap that should be enforced right now.

        -1 (unlimited, admin-set) passes through unchanged. A SUSPENDED deck
        reverts to the trial cap ("back to trial mode", #1734). Every other deck
        -- subscribed, on trial, or managed manually (no dates) -- uses its
        admin-set ``max_active_users``: new decks are created with the trial
        default (5), so the trial cap is the default, not an override, and an
        admin who deliberately raises a trial or comped deck's cap is honored.
        (Production bug find, PR 7 review: the old subscription_active-based rule
        capped comped/managed-manually decks at 5, contradicting their admin-set
        cap on the banner and subscription page.)
        """
        if self.max_active_users == -1:
            return -1
        return TRIAL_MAX_ACTIVE_USERS if self.is_suspended else self.max_active_users

    @property
    def days_until_expiry(self):
        """Days until the governing deadline: `paid_until` while a subscription is
        active, `trial_end_date` while on trial, otherwise (suspended) the LATEST
        lapsed clock.

        The latest-clock rule matters because trial_end_date is set at creation and
        never cleared when a deck subscribes: a lapsed subscriber should read as
        "expired N days ago" relative to its recent paid_until, not its ancient trial
        date. Negative once the deadline has passed (the reminder cadence keeps firing
        through the grace window); None when the deck has no dates at all
        (comped/legacy decks).
        """
        if self.subscription_active:
            deadline = self.paid_until
        elif self.is_on_trial:
            deadline = self.trial_end_date
        else:
            lapsed_clocks = [d for d in (self.trial_end_date, self.paid_until) if d is not None]
            deadline = max(lapsed_clocks) if lapsed_clocks else None
        if deadline is None:
            return None
        return (deadline - localdate()).days

    @property
    def is_over_user_limit(self):
        """Whether the deck's cached current-student count exceeds its effective cap.

        Advisory (banner/notification) check against the nightly-refreshed cached
        count -- enforcement at the registration choke points recounts live.
        Always False for unlimited (-1) decks.
        """
        if self.effective_max_active_users == -1:
            return False
        return self.active_user_count > self.effective_max_active_users

    @property
    def is_expiring_soon(self):
        """Whether the governing deadline is within EXPIRY_WARNING_DAYS (or already
        past, while still in the paid grace window) -- i.e. the status banner should
        escalate from "info" to "warning".

        False for suspended decks (they get the suspension banner instead) and for
        unmanaged/comped decks (no deadline at all).
        """
        if self.is_suspended:
            return False
        days = self.days_until_expiry
        return days is not None and days <= EXPIRY_WARNING_DAYS

    def sync_from_stripe_subscription(self, subscription):
        """The SINGLE write path from a Stripe Subscription object to this deck (plan §5.2).

        Every webhook handler, the admin "Sync from Stripe" action, and the
        nightly reconcile funnel through here -- handlers never write billing
        fields directly. Applies, with ``update_fields`` and cache invalidation:

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
        from tenant.billing import subscription_max_active_users, subscription_period_end_date
        from tenant.utils import invalidate_current_deck_cache

        status = subscription.get('status')
        # Only a PAID subscription grants anything: an 'incomplete' first payment
        # (failed 3DS) must not grant a paid period, and a 'past_due' renewal must
        # not either -- Stripe rolls current_period_end forward at renewal even
        # while the payment is still failing, and the grace period exists exactly
        # to cover that window. paid_until therefore only advances on
        # active/trialing (i.e. on payment), matching the checkout reconciler.
        grants_access = status in ('active', 'trialing')

        updates = {}
        if grants_access:
            period_end = subscription_period_end_date(subscription)
            if period_end is not None and (self.paid_until is None or period_end > self.paid_until):
                updates['paid_until'] = period_end

            cap = subscription_max_active_users(subscription)
            if cap is not None and cap != self.max_active_users:
                updates['max_active_users'] = cap

        sub_id = subscription.get('id') or ''
        if status in ('canceled', 'incomplete_expired'):
            if self.stripe_subscription_id:
                updates['stripe_subscription_id'] = ''
        elif sub_id and sub_id != self.stripe_subscription_id:
            updates['stripe_subscription_id'] = sub_id

        if updates:
            Tenant.objects.filter(pk=self.pk).update(**updates)
            for field, value in updates.items():
                setattr(self, field, value)
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
        Returns all known email addresses (verified or not) from SiteConfig().deck_owner object.
        """
        SiteConfig = apps.get_model('siteconfig', 'SiteConfig')
        owner = SiteConfig.get().deck_owner

        email = None
        # get all known email addresses, verified or not
        for email_address in EmailAddress.objects.filter(user=owner):
            # make sure it's primary email for real
            if email_address.email == user_email(owner):
                email = owner.email
        return email

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
        """
        CourseStudent = apps.get_model('courses', 'CourseStudent')
        return CourseStudent.objects.all_users_for_active_semester(students_only=True).exclude(is_superuser=True).count()

    def get_quest_count(self):
        """
        Returns the number of un-archived quests.
        """
        Quest = apps.get_model('quest_manager', 'Quest')
        return Quest.objects.filter(archived=False).count()

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
    KIND_LIMIT = 'limit'
    KIND_SUSPENDED = 'suspended'
    KIND_PAYMENT_FAILED = 'payment_failed'  # reserved for the Stripe webhook phase (plan PR 7)
    KIND_CHOICES = [
        (KIND_EXPIRY, 'Trial/subscription expiry reminder'),
        (KIND_LIMIT, 'Current-student limit warning'),
        (KIND_SUSPENDED, 'Deck suspended'),
        (KIND_PAYMENT_FAILED, 'Payment failed'),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='notices')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    threshold = models.CharField(
        max_length=20,
        help_text="Which step of the cadence fired: 'd30'/'d14'/'d7', 'daily-YYYY-MM-DD', 'pct80'/'pct100', or 'suspended'."
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
