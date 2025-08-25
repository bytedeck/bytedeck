import json

from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.template.loader import get_template

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


def generate_default_owner_password(user, tenant):
    """Generate a default password for a new deck's owner to
    firstname-deckname-lastname
    """
    return "-".join([user.first_name, tenant.name, user.last_name]).lower()


class DeckRequestService:
    """Handles deck request token generation, validation, and email sending."""

    TOKEN_MAX_AGE = 3600  # 1 hour

    @staticmethod
    def generate_token(first_name, last_name, email):
        """
        Generate a signed token encoding the user's first name, last name, and email.

        The token is timestamped and can later be validated to confirm the user's
        identity during deck creation.

        Args:
            first_name (str): User's first name.
            last_name (str): User's last name.
            email (str): User's email address.

        Returns:
            str: A signed, timestamped token containing the user info.
        """
        signer = TimestampSigner()
        payload = json.dumps({
            "first_name": first_name,
            "last_name": last_name,
            "email": email
        })
        return signer.sign(payload)

    @staticmethod
    def decode_token(token):
        """
        Decode and verify a signed deck request token.

        Validates the token's signature and ensures it is not older than TOKEN_MAX_AGE.
        Returns the decoded user data if valid, otherwise returns None.

        Args:
            token (str): A signed deck request token.

        Returns:
            dict or None: Decoded user data with keys 'first_name', 'last_name', 'email',
            or None if the token is invalid or expired.
        """
        signer = TimestampSigner()
        try:
            payload = signer.unsign(token, max_age=DeckRequestService.TOKEN_MAX_AGE)
            return json.loads(payload)
        except (BadSignature, SignatureExpired):
            return None

    @staticmethod
    def build_verification_link(request, token):
        """
        Construct a full URL for verifying a deck request token.

        Args:
            request (HttpRequest): The current request object, used to build absolute URI.
            token (str): The signed deck request token.

        Returns:
            str: A fully-qualified URL that the user can visit to verify their deck request.
        """
        from django.urls import reverse
        path = reverse("decks:verify_deck_request", args=[token])
        return request.build_absolute_uri(path)

    @staticmethod
    def send_verification_email(first_name, email, token, request=None):
        """
        Send a verification email containing a deck request token.

        If `request` is provided, builds an absolute URL using the request context.
        Otherwise, uses a relative URL.

        Args:
            first_name (str): User's first name.
            email (str): User's email address.
            token (str): Signed deck request token.
            request (HttpRequest, optional): The current request, used for building absolute URL.

        Returns:
            None
        """
        from django.urls import reverse
        if request:
            verification_link = request.build_absolute_uri(
                reverse("decks:verify_deck_request", args=[token])
            )
        else:
            verification_link = f"/decks/request-new-deck/verify/{token}/"

        message = get_template("tenant/email/verify_deck_request.txt").render({
            "first_name": first_name,
            "verification_link": verification_link,
        })

        send_email_message.delay(
            subject="Verify your email to confirm your deck request",
            message=message,
            recipient_list=[email],
        )

    @staticmethod
    def send_welcome_email(user, tenant):
        """
        Send a welcome email to a newly created tenant owner.

        The email contains information about the new tenant and the default
        owner password. It is sent asynchronously via Celery.

        Args:
            user (User): The newly created deck owner.
            tenant (Tenant): The newly created tenant instance.

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
            "password": generate_default_owner_password(user, tenant),
        })

        send_email_message.delay(
            subject=subject,
            message=message,
            recipient_list=[user.email],
        )
