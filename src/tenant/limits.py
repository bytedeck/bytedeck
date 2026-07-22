"""Live enforcement checks for deck limits (epic #1729).

Deck student-state vocabulary (maintainer definitions, PR #2077 follow-up):

* CURRENT   -- registered in a course in the active semester. Only these count
               toward deck limits.
* ACTIVE    -- every other (non-archived) student: they can sign in but aren't
               registered in a course this semester, so they don't count.
* INACTIVE  -- archived (``is_active=False``): can't sign in, listed in their
               own tab on the Students page.

Note the model fields (``max_active_users``, ``active_user_count``,
``effective_max_active_users``) predate this vocabulary and keep their legacy
"active" naming, but they meter CURRENT students.

The status banner reads nightly-cached counts, which is fine for advisory
display -- but the checks here gate the action that actually makes a student
current, so they recount LIVE to avoid racing the cache.
"""
from django.apps import apps

from siteconfig.models import SiteConfig

from tenant.utils import get_current_deck


def can_add_current_student(user):
    """Whether `user` may become a CURRENT student on this deck right now.

    Allowed when any of these hold:
    * we're not on a billable deck schema (public/library, or no Tenant row);
    * the deck's cap is unlimited (-1, admin-set);
    * the user never counts toward the cap -- staff, superusers, and test
      accounts (current-students-only counting, maintainer decision on #2047);
    * the user is already current (registered this semester, e.g. joining a
      second course) -- that's not a new seat;
    * the live current-student count is below the effective cap.

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
    already_current = CourseStudent.objects.filter(
        user=user, active=True, semester=SiteConfig.get().active_semester
    ).exists()
    if already_current:
        return True

    return deck.get_active_user_count() < cap
