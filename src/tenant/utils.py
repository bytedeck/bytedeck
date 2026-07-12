import secrets

from django.core.cache import cache
from django.template.loader import get_template
from django.urls import reverse
from django.utils.crypto import get_random_string

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

        message = get_template("tenant/email/verify_deck_request.txt").render({
            "first_name": first_name,
            "verification_link": verification_link,
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

        message = get_template("tenant/email/welcome_message.txt").render({
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
