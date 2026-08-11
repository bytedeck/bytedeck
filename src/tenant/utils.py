import secrets

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.template.loader import get_template
from django.urls import reverse
from django.utils.crypto import get_random_string

from allauth.account.models import EmailAddress
from django_tenants.utils import tenant_context

from siteconfig.models import SiteConfig
from .models import Tenant
from .tasks import send_email_message


def get_root_url():
    """
    Returns the root url of the currently connected tenant in the form of:
    scheme://[subdomain.]domain[.topleveldomain][:port]

    Port 8000 is hard coded for development

    Examples:
    - "hackerspace.bytedeck.com"
    - "hackerspace.localhost:8000"
    """
    return Tenant.get().get_root_url()


def generate_schema_name(tenant_name):
    return tenant_name.replace('-', '_').lower()


def _humanize_seconds(seconds):
    """Render a whole number of seconds as a friendly duration string.

    Used to surface the deck-request timeouts (``TOKEN_MAX_AGE`` /
    ``REQUEST_COOLDOWN``) on the confirmation page and in the verification
    email from their actual configured values, so the copy can't drift.
    Examples: ``3600 -> "1 hour"``, ``300 -> "5 minutes"``, ``90 -> "90 seconds"``.

    Args:
        seconds (int): A non-negative number of seconds.

    Returns:
        str: The duration in the largest whole unit (hours, then minutes, then
        seconds) with correct singular/plural wording.
    """
    for unit_seconds, unit_name in ((3600, "hour"), (60, "minute"), (1, "second")):
        if seconds >= unit_seconds and seconds % unit_seconds == 0:
            value = seconds // unit_seconds
            return f"{value} {unit_name}{'s' if value != 1 else ''}"
    return f"{seconds} seconds"


def generate_default_owner_password():
    """Generate a random initial password for a new deck's owner.

    Previously this was firstname-deckname-lastname, which is guessable from
    public information (all three parts are visible on the deck). A random
    password is generated once by the view, set on the owner, and emailed to
    them in the welcome message.

    Returns:
        str: A random 12-character alphanumeric initial password.
    """
    return get_random_string(12)


class DeckRequestService:
    """Handles deck-request verification and email sending.

    A deck request is verified with a single-use, opaque *nonce* rather than a
    signed token. The requester's name and email are stored server-side in the
    cache keyed by the nonce, so no personal data ever travels in the
    verification URL. (``django.core.signing`` only *signs* a payload — it does
    not encrypt it — so a signed token would leave the name/email base64-readable
    in the link, exposing them via browser history, server logs and mail
    scanners. See PR #1903.)

    The nonce is *peeked* (read, not consumed) when the email link is opened, and
    only *consumed* the first time a deck is successfully created from it, so a
    single verified request can provision at most one deck.
    """

    TOKEN_MAX_AGE = 3600  # verification validity window (seconds); also the nonce TTL
    REQUEST_COOLDOWN = 300  # min seconds between verification emails to one address
    NONCE_CACHE_PREFIX = "deck-request-nonce-"

    @staticmethod
    def _nonce_cache_key(nonce):
        """Return the cache key under which a nonce's requester data is stored.

        Args:
            nonce (str): The opaque verification nonce.

        Returns:
            str: The namespaced cache key.
        """
        return f"{DeckRequestService.NONCE_CACHE_PREFIX}{nonce}"

    @staticmethod
    def create_request(first_name, last_name, email):
        """
        Create a single-use verification nonce for a deck request.

        Generates an opaque, cryptographically-random nonce and stores the
        requester's data against it in the cache for ``TOKEN_MAX_AGE`` seconds.
        The nonce carries no personal data and is what gets embedded in the
        verification link.

        Args:
            first_name (str): User's first name.
            last_name (str): User's last name.
            email (str): User's email address.

        Returns:
            str: The opaque nonce to embed in the verification URL.
        """
        nonce = secrets.token_urlsafe(32)
        cache.set(
            DeckRequestService._nonce_cache_key(nonce),
            {"first_name": first_name, "last_name": last_name, "email": email},
            DeckRequestService.TOKEN_MAX_AGE,
        )
        return nonce

    @staticmethod
    def peek_request(nonce):
        """
        Return the requester data for a nonce *without* consuming it.

        Used at email-verification time to populate the session. The nonce is
        only consumed once a deck is actually created (see ``consume_request``),
        so re-opening the verification link before creating a deck still works.

        Args:
            nonce (str): The nonce from the verification link.

        Returns:
            dict or None: ``{'first_name', 'last_name', 'email'}`` if the nonce
            is known and unexpired, otherwise ``None``.
        """
        if not nonce:
            return None
        return cache.get(DeckRequestService._nonce_cache_key(nonce))

    @staticmethod
    def consume_request(nonce):
        """
        Atomically consume a nonce so it can create at most one deck.

        ``cache.delete()`` maps to an atomic Redis ``DEL``, so under concurrent
        deck-creation attempts exactly one caller sees a truthy result. Callers
        must only proceed with deck creation when this returns ``True``.

        Args:
            nonce (str): The nonce to consume.

        Returns:
            bool: ``True`` if this call consumed a live nonce (proceed),
            ``False`` if the nonce was missing/expired/already consumed (reject).
        """
        if not nonce:
            return False
        return bool(cache.delete(DeckRequestService._nonce_cache_key(nonce)))

    @staticmethod
    def build_verification_link(request, nonce):
        """
        Construct a full URL for verifying a deck request.

        Args:
            request (HttpRequest): The current request object, used to build absolute URI.
            nonce (str): The opaque verification nonce.

        Returns:
            str: A fully-qualified URL that the user can visit to verify their deck request.
        """
        path = reverse("decks:verify_deck_request", args=[nonce])
        return request.build_absolute_uri(path)

    @staticmethod
    def send_verification_email(first_name, email, nonce, request=None):
        """
        Send a verification email whose link carries the opaque nonce.

        If `request` is provided, builds an absolute URL using the request context.
        Otherwise, uses a relative URL.

        Args:
            first_name (str): User's first name.
            email (str): User's email address.
            nonce (str): The opaque verification nonce (no personal data).
            request (HttpRequest, optional): The current request, used for building absolute URL.

        Returns:
            None
        """
        if request is not None:
            verification_link = DeckRequestService.build_verification_link(request, nonce)
        else:
            verification_link = reverse("decks:verify_deck_request", args=[nonce])

        # rendered as the email's HTML part (send_email_message derives the
        # plain-text part from it); the shared footer supplies Bytedeck's
        # wordmark, which works here on the PUBLIC schema (no SiteConfig) because
        # it comes from settings as an absolute URL
        message = get_template("tenant/email/verify_deck_request.html").render({
            "first_name": first_name,
            "verification_link": verification_link,
            "verification_validity": _humanize_seconds(DeckRequestService.TOKEN_MAX_AGE),
        })

        # send in the background so the request doesn't block on SMTP
        send_email_message.apply_async(
            args=["Verify your email to confirm your deck request", message, [email]],
            queue="default",
        )

    @staticmethod
    def send_welcome_email(user, tenant, password):
        """
        Send a welcome email to a newly created tenant owner.

        The email contains information about the new tenant and the owner's
        initial password. It is sent asynchronously via Celery. Must be called
        from within the tenant's schema context (it reads that tenant's
        SiteConfig).

        Args:
            user (User): The newly created deck owner.
            tenant (Tenant): The newly created tenant instance.
            password (str): The owner's initial password, generated once by the
                caller so the emailed value matches the password actually set.

        Returns:
            None
        """
        subject = get_template("tenant/email/welcome_subject.txt").render({
            "config": SiteConfig.get(),
            "tenant": tenant,
            "user": user,
        })
        subject = "".join(subject.splitlines())

        # rendered as the email's HTML part (send_email_message derives the
        # plain-text part from it). A platform email, so the shared footer signs
        # it with the ByteDeck wordmark by absolute URL: a brand-new deck's
        # SiteConfig only holds the seeded default logo as a schema-relative
        # path, which mail clients render as a broken image.
        message = get_template("tenant/email/welcome_message.html").render({
            "config": SiteConfig.get(),
            "tenant": tenant,
            "user": user,
            "password": password,
        })

        # send in the background so the request doesn't block on SMTP
        send_email_message.apply_async(
            args=[subject, message, [user.email]],
            queue="default",
        )


def deck_cache_key(schema_name):
    """Cache key for the per-schema cached Tenant row used by get_current_deck."""
    return f'{schema_name}-deck'


def invalidate_current_deck_cache(schema_name):
    """Drop the cached Tenant row for a schema (called on every Tenant save).

    The cache's KEY_FUNCTION (django_tenants.cache.make_key) prefixes every key
    with the CURRENT connection's schema, and Tenant saves usually happen from
    the public schema (admin edits; later, Stripe webhooks). Deleting inside
    schema_context(schema_name) makes the prefix match the one the banner's
    get_current_deck() used when it cached the row -- without it, the delete
    silently targets a different key and the banner stays stale for up to an hour.
    """
    from django_tenants.utils import schema_context

    with schema_context(schema_name):
        cache.delete(deck_cache_key(schema_name))


def get_current_deck():
    """Return the current schema's Tenant row for status/banner display, or None.

    None on the public schema and the shared-library schema (not billable decks).
    The row is cached per schema for an hour -- mirroring the SiteConfig.get()
    pattern, since the status banner reads it on every page -- and invalidated by
    the Tenant post_save signal so admin edits (and later, Stripe syncs) show
    promptly.
    """
    from django.db import connection
    from django_tenants.utils import get_public_schema_name
    from library.utils import get_library_schema_name

    schema_name = connection.schema_name
    if schema_name in (get_public_schema_name(), get_library_schema_name()):
        return None

    cache_key = deck_cache_key(schema_name)
    deck = cache.get(cache_key)
    if deck is None:
        deck = Tenant.objects.filter(schema_name=schema_name).first()
        if deck is not None:
            cache.set(cache_key, deck, 60 * 60)
    return deck


def get_public_subscribe_url():
    """Absolute URL of the public tenant's subscribe page.

    Flatpages are per-schema, so a schema-relative "/pages/subscribe/" link 404s on
    every deck subdomain -- the banner must link to the public host explicitly.
    Mirrors Tenant.get_root_url()'s dev/production scheme handling.
    """
    from django.conf import settings

    if 'localhost' in settings.ROOT_DOMAIN:  # Development
        return f"http://{settings.ROOT_DOMAIN}:8000/pages/subscribe/"
    return f"https://{settings.ROOT_DOMAIN}/pages/subscribe/"


def normalize_owner_email(tenant, apply_changes):
    """Audit (and in apply mode normalize) one deck's owner email bookkeeping.

    The single write path behind both the ``backfill_owner_emails`` management
    command and the tenant admin's "Verify owner email" action: brings the
    deck owner up to the state deck creation produces (the ``EmailAddress`` row
    matching ``owner.email`` exists, is verified, and is the owner's only
    primary address). Must run inside the deck's tenant context.

    Args:
        tenant (Tenant): The deck being processed (its public-schema row).
        apply_changes (bool): When True, write the EmailAddress fixes and
            refresh the deck's cached fields; when False, only report.

    Returns:
        tuple: ``(status, owner_name, email, notes)`` where ``status`` is
        ``ok`` (nothing to do), ``fixed`` (bookkeeping created or corrected;
        in dry-run mode this means it WOULD be), ``no-email`` (needs a
        human), or ``skipped`` (a different account already verified the
        address, so no write can succeed: needs a human); ``owner_name`` is
        the owner's username; ``email`` is the owner's address or None;
        ``notes`` is the semicolon-joined audit remarks for the report line.
    """
    owner = SiteConfig.get().deck_owner
    notes = []
    # the initial deck_owner default was a heuristic (oldest non-admin staff
    # user, else a bare created account): flag decks that never chose for real
    if owner.username == settings.TENANT_DEFAULT_OWNER_USERNAME:
        notes.append("default owner account (heuristic guess, never chosen)")

    if not owner.email:
        return 'no-email', owner.username, None, '; '.join(notes)

    # deterministic target row, preferring the form a save lands on:
    # EmailAddress.clean() lowercases the address, so normalizing any other
    # row rewrites it to the lowercase form; targeting the lowercase row
    # first means that rewrite can never collide with a case-variant sibling
    # under the unique (user, email) constraint. Fall back to the exact-case
    # match, then the oldest case-variant duplicate.
    canonical = owner.email.lower()
    matches = list(EmailAddress.objects.filter(user=owner, email__iexact=owner.email).order_by('pk'))
    email_address = next(
        (row for row in matches if row.email == canonical),
        next((row for row in matches if row.email == owner.email), matches[0] if matches else None),
    )
    already_ok = (
        email_address is not None and email_address.verified and email_address.primary
        and not EmailAddress.objects.filter(user=owner, primary=True).exclude(pk=email_address.pk).exists()
    )
    if already_ok:
        return 'ok', owner.username, owner.email, '; '.join(notes)

    # the DB allows one VERIFIED row per address across the whole schema
    # (unique_verified_email, from ACCOUNT_UNIQUE_EMAIL): if a different
    # account already verified this address, no write can succeed, and which
    # account is really the owner's is a human call. Report and leave it.
    if EmailAddress.objects.exclude(user=owner).filter(email=canonical, verified=True).exists():
        notes.append("address already verified by another account on this deck")
        return 'skipped', owner.username, owner.email, '; '.join(notes)

    if apply_changes:
        # mirror TenantCreate.form_valid: the owner's address exists, verified
        # and primary. Every OTHER primary row is demoted BEFORE the target
        # saves: the DB allows at most one primary per user
        # (unique_primary_email), so the demote must come first, and excluding
        # by pk (a brand-new target has none, so nothing is spared) also
        # demotes a case-variant duplicate of the owner's own address.
        if email_address is None:
            email_address = EmailAddress(user=owner, email=owner.email, verified=True, primary=True)
        else:
            email_address.verified = True
            email_address.primary = True
        EmailAddress.objects.filter(user=owner, primary=True).exclude(pk=email_address.pk).update(primary=False)
        email_address.full_clean()
        email_address.save()
        # land owner_email_cached now; the notice engine and the Stripe
        # backfill report read the cache, not the schema
        tenant.update_cached_fields()
    return 'fixed', owner.username, owner.email, '; '.join(notes)


def switch_deck_owner(tenant, username):
    """Make ``username`` (an existing STAFF user on the deck) the deck's owner.

    The single write path behind both the ``change_deck_owner`` management
    command and the tenant admin's "Change deck owner" action. Mirrors the
    SiteConfig admin's semantics (``SiteConfigForm.clean_deck_owner``): the new
    owner is promoted to superuser, and the previous owner's account and
    permissions are left untouched. The deck's cached owner fields are
    refreshed immediately so the public admin, the notice engine, and the
    Stripe backfill report see the new owner without waiting for the nightly
    task. When the user already owns the deck, nothing is written.

    Args:
        tenant (Tenant): The deck whose owner changes (its public-schema row).
        username (str): The new owner's username on that deck.

    Returns:
        tuple[str, str]: ``(old_username, new_username)``; equal when the user
        already owned the deck and nothing was written.

    Raises:
        ValueError: When no such user exists on the deck, or the user is not staff.
    """
    User = get_user_model()
    with transaction.atomic(), tenant_context(tenant):
        try:
            new_owner = User.objects.get(username=username)
        except User.DoesNotExist:
            raise ValueError(f"no user '{username}' exists on deck '{tenant.schema_name}'")
        if not new_owner.is_staff:
            raise ValueError(
                f"'{username}' is not a staff user on '{tenant.schema_name}': the deck owner must be "
                "staff. Make them staff first if this really is the right account."
            )
        config = SiteConfig.get()
        old_owner = config.deck_owner
        # the field is NOT NULL, but older admin code guards ownerless decks
        # (message_selected), so surface the state through the ValueError channel
        # the callers already handle rather than an AttributeError below
        if old_owner is None:
            raise ValueError(
                f"deck '{tenant.schema_name}' has no owner set in its SiteConfig; fix it there first"
            )
        if old_owner == new_owner:
            return old_owner.username, new_owner.username
        # mirror SiteConfigForm.clean_deck_owner: the deck owner is always a superuser.
        # A narrow update_fields save so a concurrent edit to any OTHER column of
        # this user row can't be clobbered; like the mirrored admin path, no
        # full_clean here: validating the whole (possibly legacy) user row could
        # block the promotion on data unrelated to the one boolean changing.
        if not new_owner.is_superuser:
            new_owner.is_superuser = True
            new_owner.save(update_fields=['is_superuser'])
        config.deck_owner = new_owner
        config.full_clean()
        config.save()
        # land the cached owner name/email now; the public admin, the notice
        # engine, and the Stripe backfill report all read the cache
        tenant.update_cached_fields()
    return old_owner.username, new_owner.username
