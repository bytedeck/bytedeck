"""Live enforcement checks for deck limits (epic #1729 PR 4).

The status banner (PR 3) reads nightly-cached counts, which is fine for advisory
display -- but the checks here gate the action that actually creates an active
student, so they recount LIVE to avoid racing the cache.
"""
from django.apps import apps

from siteconfig.models import SiteConfig

from tenant.utils import get_current_deck


def can_add_active_user(user):
    """Whether `user` may become an active student on this deck right now.

    Allowed when any of these hold:
    * we're not on a billable deck schema (public/library, or no Tenant row);
    * the deck's cap is unlimited (-1, admin-set);
    * the user never counts toward the cap -- staff, superusers, and test
      accounts (students-only counting, maintainer decision on #2047);
    * the user already counts (already actively registered this semester, e.g.
      joining a second course) -- that's not a NEW seat;
    * the live active-student count is below the effective cap.

    Refused only when granting a brand-new seat would exceed the cap.

    Args:
        user (User): the prospective course registrant.

    Returns:
        bool: True when registration may proceed.
    """
    deck = get_current_deck()
    if deck is None:
        return True

    cap = deck.effective_max_active_users
    if cap == -1:
        return True

    if user.is_staff or user.is_superuser or user.profile.is_test_account:
        return True

    CourseStudent = apps.get_model('courses', 'CourseStudent')
    already_counted = CourseStudent.objects.filter(
        user=user, active=True, semester=SiteConfig.get().active_semester
    ).exists()
    if already_counted:
        return True

    return deck.get_active_user_count() < cap
