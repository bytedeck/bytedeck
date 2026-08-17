from allauth.account.models import EmailAddress
from django.contrib.auth import get_user_model

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from profile_manager.models import Profile
from siteconfig.models import SiteConfig
from courses.models import CourseStudent, Course, Semester

User = get_user_model()


class ProfileManagerTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create staff plus active/inactive students in and out of the active semester."""
        cls.course = baker.make(Course)
        cls.active_semester = SiteConfig.get().active_semester

        # staff
        cls.staff_set = list(User.objects.filter(is_staff=True)) + [baker.make(User, username='teacher', is_staff=True)]

        # for naming students so when qs isn't equal the names are readable
        names = [f'user-{index}' for index in range(8)][::-1]  # reverse for pop method

        # students not in active sem
        cls.active_inactive_semester_students = baker.make(User, username=names.pop, _quantity=2)
        cls.inactive_inactive_semester_students = baker.make(User, username=names.pop, _quantity=2, is_active=False)
        cls.inactive_semester_students = cls.active_inactive_semester_students + cls.inactive_inactive_semester_students

        for user in cls.inactive_semester_students:
            baker.make(
                CourseStudent,
                user=user,
                course=cls.course
            )

        # students in active sem
        cls.active_active_semester_students = baker.make(User, username=names.pop, _quantity=2)
        cls.inactive_active_semester_students = baker.make(User, username=names.pop, _quantity=2, is_active=False)
        cls.active_semester_students = cls.active_active_semester_students + cls.inactive_active_semester_students

        for user in cls.active_semester_students:
            baker.make(
                CourseStudent,
                user=user,
                course=cls.course,
                semester=cls.active_semester
            )

    def test_all_in_open_semesters__returns_active_students(self):
        """all_in_open_semesters() returns only active students registered in an open semester."""
        qs = Profile.objects.all_in_open_semesters().values_list('user__username', flat=True)
        expected_qs = self.active_active_semester_students
        expected_qs = [user.username for user in expected_qs]

        self.assertEqual(set(qs), set(expected_qs))

    def test_all_in_open_semesters__includes_a_second_open_semester(self):
        """A student in another open semester is taking a course too, so they belong in the
        current-students list rather than only the cohort the deck's pointer names."""
        other_student = baker.make(User, username='second_cohort')
        baker.make(
            CourseStudent, user=other_student, course=self.course,
            semester=baker.make(Semester, status=Semester.Status.OPEN),
        )

        usernames = Profile.objects.all_in_open_semesters().values_list('user__username', flat=True)

        self.assertIn('second_cohort', usernames)

    def make_verified_recipient(self, username, **user_kwargs):
        """Create a user who wants announcement email and whose address is verified, so
        get_mailing_list() has no reason of its own to leave them out."""
        user = baker.make(User, username=username, email=f'{username}@bytedeck.com', **user_kwargs)
        user.profile.get_announcements_by_email = True
        user.profile.save()
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        return user

    def test_get_mailing_list__excludes_an_enrolled_test_account(self):
        """A test account exists so a teacher can see the student view without being a real
        recipient, so enrolling one in a course must not put the address behind it on the
        deck's mailing list (issue #2434)."""
        test_account = self.make_verified_recipient('test_account')
        test_account.profile.is_test_account = True
        test_account.profile.save()
        baker.make(CourseStudent, user=test_account, course=self.course, semester=self.active_semester)

        emails = Profile.objects.get_mailing_list(as_emails_list=True, for_announcement_email=True)

        self.assertNotIn(test_account.email, emails)

    def test_get_mailing_list__includes_an_enrolled_student(self):
        """The other side of the same filter: an ordinary student in a course is exactly who
        the mailing list is for."""
        student = self.make_verified_recipient('mailing_list_student')
        baker.make(CourseStudent, user=student, course=self.course, semester=self.active_semester)

        emails = Profile.objects.get_mailing_list(as_emails_list=True, for_announcement_email=True)

        self.assertIn(student.email, emails)

    def test_get_mailing_list__keeps_a_teacher_enrolled_in_a_course(self):
        """Staff are dropped from the student half of the list, and picked up again by the
        teacher half, so a teacher who is also registered in a course still gets the email
        (once: the two halves are merged with distinct())."""
        teacher = self.make_verified_recipient('enrolled_teacher', is_staff=True)
        baker.make(CourseStudent, user=teacher, course=self.course, semester=self.active_semester)

        emails = Profile.objects.get_mailing_list(as_emails_list=True, for_announcement_email=True)

        self.assertEqual(emails.count(teacher.email), 1)

    def test_all_active__returns_active_users(self):
        """all_active() returns every active user, including staff, regardless of semester."""
        qs = Profile.objects.all_active().values_list('user__username', flat=True)
        expected_qs = self.active_inactive_semester_students + self.active_active_semester_students + self.staff_set
        expected_qs = [user.username for user in expected_qs]

        self.assertEqual(set(qs), set(expected_qs))

    def test_all_inactive__returns_inactive_users(self):
        """all_inactive() returns only the deactivated users."""
        qs = Profile.objects.all_inactive().values_list('user__username', flat=True)
        expected_qs = self.inactive_inactive_semester_students + self.inactive_active_semester_students
        expected_qs = [user.username for user in expected_qs]

        self.assertEqual(set(qs), set(expected_qs))
