# import djconfig
from django.contrib.auth import get_user_model
from django.test import TestCase
from model_mommy import mommy
# from model_mommy.recipe import Recipe

from courses.models import MarkRange, Course

User = get_user_model()


class MarkRangeTestModel(TestCase):

    def setUp(self):
        self.mr_50 = mommy.make(MarkRange, minimum_mark=50.0)
        # djconfig.reload_maybe()  # https://github.com/nitely/django-djconfig/issues/31#issuecomment-451587942

        # self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        # self.user = mommy.make(User)
        # Profiles are created automatically with each user, so we only need to access profiles via users
        # self.profile = self.user.profile

        # self.active_sem = mommy.make(Semester, pk=djconfig.config.hs_active_semester)

        # Why is this required?  Why can't I just mommy.make(Semester)?  For some reason when I
        # use mommy.make(Semester) it tried to duplicate the pk, using pk=1 again?!
        # self.inactive_sem = mommy.make(Semester, pk=djconfig.config.hs_active_semester+1)

    def test_marke_range_creation(self):
        self.assertIsInstance(self.mr_50, MarkRange)
        # self.assertEqual(str(self.mr_50), self.user.username)


class MarkRangeTestManager(TestCase):
    def setUp(self):
        self.mr_50 = mommy.make(MarkRange, minimum_mark=50.0)

    def test_get_range(self):
        self.mr_75 = mommy.make(MarkRange, minimum_mark=75.0)
        self.mr_100 = mommy.make(MarkRange, minimum_mark=100.0)

        self.assertEqual(MarkRange.objects.get_range(25.0), None)
        self.assertEqual(MarkRange.objects.get_range(50.0), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(74.9), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(75.0), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0), self.mr_100)

    def test_get_range_with_course(self):
        c1 = mommy.make(Course)
        c2 = mommy.make(Course)
        self.mr_50_c1 = mommy.make(MarkRange, minimum_mark=50.0, courses=[c1])
        self.mr_50_c2 = mommy.make(MarkRange, minimum_mark=50.0, courses=[c2])
        self.mr_75 = mommy.make(MarkRange, minimum_mark=75.0)
        self.mr_100_c1 = mommy.make(MarkRange, minimum_mark=100.0, courses=[c1])

        self.assertEqual(MarkRange.objects.get_range(25.0), None)
        self.assertEqual(MarkRange.objects.get_range(50.0), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(50.0, [c1]), self.mr_50_c1)
        self.assertEqual(MarkRange.objects.get_range(74.9, [c2]), self.mr_50_c2)
        self.assertEqual(MarkRange.objects.get_range(74.9), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(75.0, [c1]), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(75.0), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0, [c2]), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0, [c1, c2]), self.mr_100_c1)
