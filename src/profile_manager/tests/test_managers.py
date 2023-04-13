from django.contrib.auth import get_user_model
from django_tenants.test.cases import TenantTestCase

from model_bakery import baker

from profile_manager.models import Profile
from siteconfig.models import SiteConfig
from courses.models import CourseStudent, Course

User = get_user_model()


class ProfileManagerTest(TenantTestCase):

    def setUp(self):
        self.course = baker.make(Course)
        self.active_semester = SiteConfig().get().active_semester

        # staff
        self.staff_set = list(User.objects.filter(is_staff=True)) + [baker.make(User, username='teacher', is_staff=True)]

        # for naming students so when qs isn't equal the names are readable
        names = [f'user-{index}' for index in range(8)][::-1]  # reverse for pop method

        # students not in active sem
        self.active_inactive_semester_students = baker.make(User, username=names.pop, _quantity=2)
        self.inactive_inactive_semester_students = baker.make(User, username=names.pop, _quantity=2, is_active=False)
        self.inactive_semester_students = self.active_inactive_semester_students + self.inactive_inactive_semester_students

        for user in self.inactive_semester_students:
            baker.make(
                CourseStudent,
                user=user,
                course=self.course
            )

        # students in active sem
        self.active_active_semester_students = baker.make(User, username=names.pop, _quantity=2)
        self.inactive_active_semester_students = baker.make(User, username=names.pop, _quantity=2, is_active=False)
        self.active_semester_students = self.active_active_semester_students + self.inactive_active_semester_students

        for user in self.active_semester_students:
            baker.make(
                CourseStudent,
                user=user,
                course=self.course,
                semester=self.active_semester
            )

    def test_all_for_active_semester_qs(self):
        qs = Profile.objects.all_for_active_semester().values_list('user__username', flat=True)
        expected_qs = self.active_active_semester_students
        expected_qs = [user.username for user in expected_qs]

        self.assertEqual(set(qs), set(expected_qs))

    def test_get_active_qs(self):
        qs = Profile.objects.all_active().values_list('user__username', flat=True)
        expected_qs = self.active_inactive_semester_students + self.active_active_semester_students + self.staff_set
        expected_qs = [user.username for user in expected_qs]

        self.assertEqual(set(qs), set(expected_qs))

    def test_get_inactive_qs(self):
        qs = Profile.objects.all_inactive().values_list('user__username', flat=True)
        expected_qs = self.inactive_inactive_semester_students + self.inactive_active_semester_students
        expected_qs = [user.username for user in expected_qs]

        self.assertEqual(set(qs), set(expected_qs))
