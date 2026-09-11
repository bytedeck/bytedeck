from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils.timezone import localdate

from django_tenants.utils import get_public_schema_name, schema_context
from model_bakery import baker

from courses.models import Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig
from tenant.limits import can_add_current_student
from tenant.utils import deck_cache_key

User = get_user_model()


class CanAddCurrentStudentTest(ByteDeckTenantTestCase):
    """Tests for the live current-student cap check gating course registration (#1729 PR 4)."""

    def setUp(self):
        """Give this deck a subscribed cap of 1 so the cap is easy to hit, and clear
        the deck cache (the cache backend outlives each test's transaction)."""
        cache.delete(deck_cache_key(self.tenant.schema_name))
        self.tenant.paid_until = localdate() + timedelta(days=30)
        self.tenant.max_active_users = 1
        self.tenant.save()

    def fill_the_single_seat(self):
        """Register one student in the active semester, consuming the deck's only seat."""
        student = baker.make(User)
        baker.make('courses.CourseStudent', user=student, active=True, semester=SiteConfig.get().active_semester)
        return student

    def test_can_add_current_student__allowed_below_cap_refused_at_cap(self):
        """A new student gets the last free seat; the next one is refused."""
        newcomer = baker.make(User)
        self.assertTrue(can_add_current_student(newcomer))

        self.fill_the_single_seat()
        self.assertFalse(can_add_current_student(newcomer))

    def test_can_add_current_student__already_registered_student_is_not_a_new_seat(self):
        """A student who already counts (registered this semester) may register again
        (e.g. a second course) even with the deck at its cap."""
        occupant = self.fill_the_single_seat()
        self.assertTrue(can_add_current_student(occupant))

    def test_can_add_current_student__no_open_semester_frees_the_seats(self):
        """Archiving the semester frees every seat (that is what it is for), so the deck is
        no longer at its cap even though the registrations are still there."""
        occupant = self.fill_the_single_seat()
        self.assertFalse(can_add_current_student(baker.make(User)))

        Semester.objects.complete_semester()

        self.assertTrue(can_add_current_student(baker.make(User)))
        self.assertTrue(can_add_current_student(occupant))

    def test_can_add_current_student__seat_is_held_in_whichever_semester_they_joined(self):
        """A student in the open semester the deck's pointer does not name still holds their
        seat, so adding a second course does not ask for another one (issue #2157 Phase 3).
        Reading the deck's pointer instead would treat them as a newcomer and refuse them
        once the deck is full."""
        other_semester = baker.make(Semester, status=Semester.Status.OPEN)
        occupant = baker.make(User)
        baker.make('courses.CourseStudent', user=occupant, active=True, semester=other_semester)

        self.assertTrue(can_add_current_student(occupant))
        self.assertFalse(can_add_current_student(baker.make(User)))  # the deck is full because of them

    def test_can_add_current_student__staff_superusers_and_test_accounts_never_blocked(self):
        """Users who never count toward the cap (students-only counting, #2047) are
        never refused, even at the cap."""
        self.fill_the_single_seat()

        self.assertTrue(can_add_current_student(baker.make(User, is_staff=True)))
        self.assertTrue(can_add_current_student(baker.make(User, is_superuser=True, is_staff=False)))

        test_account = baker.make(User)
        test_account.profile.is_test_account = True
        test_account.profile.save()
        self.assertTrue(can_add_current_student(test_account))

    def test_can_add_current_student__unlimited_deck_never_blocked(self):
        """A deck with the -1 unlimited sentinel never refuses a registration."""
        self.tenant.max_active_users = -1
        self.tenant.save()
        self.fill_the_single_seat()
        self.assertTrue(can_add_current_student(baker.make(User)))

    def test_can_add_current_student__no_deck_schema_never_blocked(self):
        """On a schema with no billable deck (e.g. public), the check is a no-op."""
        user = baker.make(User)
        with schema_context(get_public_schema_name()):
            self.assertTrue(can_add_current_student(user))
