# import djconfig
from datetime import timedelta, date
from freezegun import freeze_time

from django.contrib.auth import get_user_model
from django.test import TestCase
from model_mommy import mommy
# from model_mommy.recipe import Recipe

from courses.models import MarkRange, Course, Semester

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


class SemesterTestModel(TestCase):

    def setUp(self):
        self.semester_start = date(2020, 9, 8)
        self.semester_end = date(2021, 1, 22)
        self.today_fake = date(2020, 10, 20)  # some date in the semester
        self.semester = mommy.make(Semester,
                                   number=Semester.SEMESTER_CHOICES[1][1],
                                   first_day=self.semester_start,
                                   last_day=self.semester_end
                                   )

    def test_semester_creation(self):
        self.assertIsInstance(self.semester, Semester)
        self.assertEqual(str(self.semester), self.semester.first_day.strftime("%b-%Y"))

    def test_is_open(self):
        # before semester starts: False
        before_start = self.semester_start - timedelta(days=1)
        with freeze_time(before_start, tz_offset=0):
            self.assertFalse(self.semester.is_open())

        # after semester ends: False
        after_end = self.semester_end + timedelta(days=1)
        with freeze_time(after_end, tz_offset=0):
            self.assertFalse(self.semester.is_open())

        # during semester: True
        during = self.semester_start + timedelta(days=1)
        with freeze_time(during, tz_offset=0):
            self.assertTrue(self.semester.is_open())

        # first day: True
        with freeze_time(self.semester_start, tz_offset=0):
            self.assertTrue(self.semester.is_open())
        # last day: True
        with freeze_time(self.semester_end, tz_offset=0):
            self.assertTrue(self.semester.is_open())

        # Timezone problems?    


class CourseTestModel(TestCase):

    def setUp(self):
        self.course = mommy.make(Course)

    def test_semester_creation(self):
        self.assertIsInstance(self.course, Course)
        self.assertEqual(str(self.course), self.course.title)

    # def test condition_met_as_prerequisite(self):
    #     pass
