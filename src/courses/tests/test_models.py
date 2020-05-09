from datetime import timedelta, date
from django.contrib.auth import get_user_model

from model_bakery import baker
from freezegun import freeze_time
from tenant_schemas.test.cases import TenantTestCase

from courses.models import MarkRange, Course, Semester, Block, Rank

User = get_user_model()


class MarkRangeTestModel(TenantTestCase):

    def setUp(self):
        self.mr_50 = baker.make(MarkRange, minimum_mark=50.0)

    def test_marke_range_creation(self):
        self.assertIsInstance(self.mr_50, MarkRange)
        # self.assertEqual(str(self.mr_50), self.user.username)


class MarkRangeTestManager(TenantTestCase):
    def setUp(self):
        self.mr_50 = baker.make(MarkRange, minimum_mark=50.0)

    def test_get_range(self):
        self.mr_75 = baker.make(MarkRange, minimum_mark=75.0)
        self.mr_100 = baker.make(MarkRange, minimum_mark=100.0)

        self.assertEqual(MarkRange.objects.get_range(25.0), None)
        self.assertEqual(MarkRange.objects.get_range(50.0), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(74.9), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(75.0), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0), self.mr_100)

    def test_get_range_with_course(self):
        c1 = baker.make(Course)
        c2 = baker.make(Course)
        self.mr_50_c1 = baker.make(MarkRange, minimum_mark=50.0, courses=[c1])
        self.mr_50_c2 = baker.make(MarkRange, minimum_mark=50.0, courses=[c2])
        self.mr_75 = baker.make(MarkRange, minimum_mark=75.0)
        self.mr_100_c1 = baker.make(MarkRange, minimum_mark=100.0, courses=[c1])

        self.assertEqual(MarkRange.objects.get_range(25.0), None)
        self.assertEqual(MarkRange.objects.get_range(50.0), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(50.0, [c1]), self.mr_50_c1)
        self.assertEqual(MarkRange.objects.get_range(74.9, [c2]), self.mr_50_c2)
        self.assertEqual(MarkRange.objects.get_range(74.9), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(75.0, [c1]), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(75.0), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0, [c2]), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0, [c1, c2]), self.mr_100_c1)


class SemesterTestModel(TenantTestCase):

    def setUp(self):
        self.semester_start = date(2020, 9, 8)
        self.semester_end = date(2021, 1, 22)
        self.today_fake = date(2020, 10, 20)  # some date in the semester
        self.semester = baker.make(Semester,
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


class CourseTestModel(TenantTestCase):

    def setUp(self):
        self.course = baker.make(Course)

    def test_semester_creation(self):
        self.assertIsInstance(self.course, Course)
        self.assertEqual(str(self.course), self.course.title)

    # def test condition_met_as_prerequisite(self):
    #     pass

    def test_default_object_created(self):
        """ A data migration should make a default object for this model """
        self.assertTrue(Course.objects.filter(title="Default").exists())


class BlockModelTest(TenantTestCase):
    
    def test_default_object_created(self):
        """ A data migration should make a default block """
        self.assertTrue(Block.objects.filter(block="Default").exists())


class RankModelTest(TenantTestCase):
    
    def test_default_object_created(self):
        """ A data migration should make default objects for this model """
        self.assertTrue(Rank.objects.filter(name="Digital Noob").exists())
        self.assertEqual(Rank.objects.count(), 13)


class GradeModelTest(TenantTestCase):
    
    def test_default_object_created(self):
        """ A data migration should make default objects for this model """
        self.assertTrue(Rank.objects.filter(name="12").exists())
        self.assertEqual(Rank.objects.count(), 5)
