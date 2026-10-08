"""Middleware for profiles."""
from datetime import timedelta

from django.db import connection
from django.utils import timezone
from django_tenants.utils import get_public_schema_name

from profile_manager.models import Profile

#: The most often a person's last activity is written down: the profile and the student list
#: show it to the day, so anything finer would only add database writes.
LAST_ACTIVE_INTERVAL = timedelta(hours=1)

#: The session key holding when this browser last recorded the person's activity, as a POSIX
#: timestamp, so most requests can skip the write without a database read.
LAST_ACTIVE_SESSION_KEY = "last_active_recorded"

#: Requests an open page makes on its own, on a timer: the notification and approvals badges
#: refresh themselves, so a tab left open would otherwise count as someone using the deck.
BACKGROUND_URL_NAMES = frozenset({"notifications:ajax", "quests:ajax_submission_count"})


class LastActiveMiddleware:
    """Record when each signed-in person last used their deck, in `Profile.last_active` (#2849).

    A session lasts weeks, so the user's `last_login` changes only when they sign in again, and a
    student who stays signed in shows a sign-in date far older than their last visit. This writes
    the time after the person's request is answered, at most once an hour per browser, skipping
    the public site (which has no profiles) and the badge refreshes an open page makes on its own.
    """

    def __init__(self, get_response):
        """Store the next callable, per Django's middleware contract."""
        self.get_response = get_response

    def __call__(self, request):
        """Answer the request, then record the person's activity if it's due.

        After the view rather than before it, so the url the request resolved to is known, and so
        a request that signs the person in or out is judged by who they are once it's done.
        """
        response = self.get_response(request)
        if self.is_due(request):
            now = timezone.now()
            Profile.objects.filter(user_id=request.user.pk).update(last_active=now)
            request.session[LAST_ACTIVE_SESSION_KEY] = now.timestamp()
        return response

    @staticmethod
    def is_due(request):
        """Whether this request should record its person's activity.

        Args:
            request (HttpRequest): the request, once answered.

        Returns:
            bool: True for a signed-in person on a deck whose activity this browser hasn't
            recorded within `LAST_ACTIVE_INTERVAL`, unless the request is a background refresh.
        """
        if not request.user.is_authenticated or connection.schema_name == get_public_schema_name():
            return False
        # None for a url that resolved to no view (a 404)
        match = request.resolver_match
        if match is not None and match.view_name in BACKGROUND_URL_NAMES:
            return False
        recorded = request.session.get(LAST_ACTIVE_SESSION_KEY)
        return recorded is None or timezone.now().timestamp() - recorded >= LAST_ACTIVE_INTERVAL.total_seconds()
