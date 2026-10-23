"""Request-time enforcement of the deck suspension policy (epic #1729, #1734)."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect

from siteconfig.models import SiteConfig
from tenant.utils import get_current_deck

SUSPENDED_SIGN_OUT_MESSAGE = (
    "You have been signed out: this deck is suspended, and only the deck owner "
    "can sign in until the deck has a valid subscription."
)


class OwnerOnlyWhenSuspendedMiddleware:
    """On a suspended deck, sign out every authenticated user except the deck owner.

    The suspension policy (maintainer redesign, 2026-07-30): a suspended deck is
    closed to everyone but its owner until it has a valid subscription again
    (any level, including Maintenance). Enforcement is request-time rather than
    login-time because sessions outlive the suspension moment (8-week
    SESSION_COOKIE_AGE): a login-form gate would leave already-signed-in
    students and staff working for weeks into a suspension, and would miss
    Google sign-ins. A bounced user is signed out, shown a message, and
    redirected to the sign-in page (where the status banner repeats the rule).

    Pass-through cases:
    * anonymous requests (the sign-in page itself, static assets, webhooks);
    * the public and shared-library schemas (get_current_deck returns None);
    * decks that aren't suspended;
    * the deck owner (SiteConfig.deck_owner);
    * the ByteDeck support account (TENANT_DEFAULT_ADMIN_USERNAME), so
      operators can always reach a suspended deck.
    """

    def __init__(self, get_response):
        """Store the next callable, per Django's middleware contract."""
        self.get_response = get_response

    def __call__(self, request):
        """Bounce an authenticated non-owner off a suspended deck; otherwise pass through."""
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            deck = get_current_deck()
            if deck is not None and deck.is_suspended and not self._may_stay(user):
                logout(request)
                messages.error(request, SUSPENDED_SIGN_OUT_MESSAGE)
                return redirect('account_login')
        return self.get_response(request)

    @staticmethod
    def _may_stay(user):
        """Whether this user keeps access on a suspended deck: the deck owner or the support admin."""
        if user.get_username() == settings.TENANT_DEFAULT_ADMIN_USERNAME:
            return True
        return SiteConfig.get().deck_owner_id == user.pk
