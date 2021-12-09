from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from freezegun import freeze_time
from mock import patch
from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase

from courses.models import Block, Course, CourseStudent, ExcludedDate, Grade, MarkRange, Rank, Semester
from siteconfig.models import SiteConfig

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


class BlockModelManagerTest(TenantTestCase):

    def test_grouped_teachers_blocks_equals_one(self):
        """ Should only return 1 group of teachers if regardless of the number of Blocks """

        teacher_admin = User.objects.get(username='admin')

        for _ in range(5):
            baker.make(Block, current_teacher=teacher_admin)

        group = Block.objects.grouped_teachers_blocks()

        self.assertEqual(len(group.keys()), 1)

    def test_grouped_teachers_blocks_more_than_one(self):
        """ Should return 3 group of teachers teaching Default, [AB] and [CD] blocks"""

        teacher_admin = User.objects.get(username='admin')
        teacher1 = baker.make(User, username='teacher1', is_staff=True)
        teacher2 = baker.make(User, username='teacher2', is_staff=True)

        block_default = Block.objects.get(block='Default')
        block_a = baker.make(Block, block='A', current_teacher=teacher1)
        block_b = baker.make(Block, block='B', current_teacher=teacher1)
        block_c = baker.make(Block, block='C', current_teacher=teacher2)
        block_d = baker.make(Block, block='D', current_teacher=teacher2)

        group = Block.objects.grouped_teachers_blocks()

        # Should assert to 3 groups
        self.assertEqual(len(group.keys()), 3)

        # admin teaches default block
        self.assertListEqual(group[teacher_admin.id], [block_default.block])
        # teacher1 teaches A and B block
        self.assertListEqual(group[teacher1.id], [block_a.block, block_b.block])
        # teacher2 teaches C and D block
        self.assertListEqual(group[teacher2.id], [block_c.block, block_d.block])


class SemesterModelManagerTest(TenantTestCase):
    def setUp(self):
        self.semester_start = date(2019, 9, 1)  # Sep 1st 2019
        self.semester_end = date(2019, 9, 30)  # Sep 30th, 2019
        self.semester1 = baker.make(Semester, first_day=self.semester_start, last_day=self.semester_end)

    def test_get_current(self):
        """ Get's the current semester as defined by SiteConfig """
        self.assertEqual(Semester.objects.get_current(), SiteConfig.get().active_semester)

    def test_get_current_as_queryset(self):
        """ Get's the current semester object in a quesryset  """
        self.assertQuerysetEqual(Semester.objects.get_current(as_queryset=True), [repr(SiteConfig.get().active_semester)])

    def test_complete_active_semester(self):
        """ set current semester to closed and do lots of stuff..  """
        # TODO
        pass


class SemesterModelTest(TenantTestCase):

    def setUp(self):
        self.semester_start = date(2019, 9, 1)  # Sep 1st 2019
        self.semester_end = date(2019, 9, 30)  # Sep 30th, 2019
        self.today_fake = date(2019, 9, 15)  # Sep 15 2019, some date in the semester
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

    def test_num_days(self):
        """The number of classes in the semester, from start to end date excluding weekends and excluded dates
        """
        # no excluded dates yet, so 21 weekdays in Sep 2019 (see setup)
        self.assertEqual(self.semester.num_days(), 21)

        # add some excluded dates
        baker.make(ExcludedDate, semester=self.semester, date=date(2019, 9, 1))  # Sun, shouldn't count
        baker.make(ExcludedDate, semester=self.semester, date=date(2019, 9, 2))  # Mon
        self.assertEqual(self.semester.num_days(), 20)

        # Future dates should only go up to end.
        with freeze_time(date(2019, 10, 15), tz_offset=0):
            self.assertEqual(self.semester.num_days(upto_today=True), 20)

        self.assertIsInstance(self.semester.num_days(), int)

    def test_num_days_upto_today(self):
        """The number of classes in the semester SO FAR up to today
        """
        with freeze_time(date(2019, 9, 15), tz_offset=0):
            self.assertEqual(self.semester.num_days(upto_today=True), 10)

        # Future dates should only go up to end.
        with freeze_time(date(2019, 10, 15), tz_offset=0):
            self.assertEqual(self.semester.num_days(upto_today=True), 21)

    def test_excluded_days(self):
        """ returns a list of dates excluded for this semester (holidays and other non-instructional days) """
        # add some excluded dates
        baker.make(ExcludedDate, semester=self.semester, date=date(2019, 9, 1))  # Sun, shouldn't count
        baker.make(ExcludedDate, semester=self.semester, date=date(2019, 9, 2))  # Mon

        dates = self.semester.excluded_days()
        self.assertListEqual(list(dates), [date(2019, 9, 1), date(2019, 9, 2)])

    def test_days_so_far(self):
        self.assertEqual(self.semester.days_so_far(), self.semester.num_days(upto_today=True))

    def test_fraction_complete(self):
        """ how far through the semester as a fraction """
        with freeze_time(date(2019, 9, 15), tz_offset=0):
            # 10 days so far (excluding weekends) / 21 days total
            fraction_complete = self.semester.fraction_complete()
            self.assertAlmostEqual(fraction_complete, 10 / 21)

    def test_percent_complete(self):
        """ how far through the semester as a percent """
        with freeze_time(date(2019, 9, 15), tz_offset=0):
            # 10 days so far (excluding weekends) / 21 days total * 100
            percent_complete = self.semester.percent_complete()
            self.assertAlmostEqual(percent_complete, 10 / 21 * 100)

    def test_get_interim1_date(self):
        self.assertEqual(self.semester.get_interim1_date(), self.semester.get_date(0.25))

    def test_get_term_date(self):
        self.assertEqual(self.semester.get_term_date(), self.semester.get_date(0.5))

    def test_get_interim2_date(self):
        self.assertEqual(self.semester.get_interim2_date(), self.semester.get_date(0.75))

    def test_get_final_date(self):
        self.assertEqual(self.semester.get_final_date(), self.semester.last_day)

    def test_get_date(self):
        """ Gets the closest date, rolling back if it falls on a weekend or excluded
        after a fraction of the semester is over """
        self.assertEqual(self.semester.get_date(0.25), date(2019, 9, 6))
        self.assertEqual(self.semester.get_date(0.5), date(2019, 9, 13))  # lands on a weekend so roll back to the friday
        self.assertEqual(self.semester.get_date(1.0), self.semester.last_day)

    def test_get_datetime_by_days_since_start(self):
        """ 5 days since start of semester should fall on 6 Sep 2019,
        6 days should push through weekend and land on 9 Sep 2019 """
        dt = self.semester.get_datetime_by_days_since_start(5)
        expected = timezone.make_aware(datetime(2019, 9, 6, 23, 59, 59, 999999), timezone.get_default_timezone())
        self.assertEqual(dt, expected)

        dt = self.semester.get_datetime_by_days_since_start(6)
        expected = timezone.make_aware(datetime(2019, 9, 9, 23, 59, 59, 999999), timezone.get_default_timezone())
        self.assertEqual(dt, expected)

    def test_reset_students_xp_cached(self):
        """Students' xp_cached should be set to 0."""
        student = baker.make(User)
        course = baker.make(Course)
        active_semester = SiteConfig.get().active_semester

        student.profile.xp_cached = 100
        student.profile.save()

        baker.make(CourseStudent, user=student, course=course, semester=active_semester)

        active_semester.reset_students_xp_cached()
        self.assertEqual(student.profile.xp_cached, 0)


class CourseModelTest(TenantTestCase):

    def setUp(self):
        self.course = baker.make(Course)

    def test_course_creation(self):
        self.assertIsInstance(self.course, Course)
        self.assertEqual(str(self.course), self.course.title)

    def test_condition_met_as_prerequisite(self):
        """ If the user is CURRENTLY registered in this course, then condition is met """
        student = baker.make(User)
        baker.make(CourseStudent, user=student, course=self.course)
        self.assertFalse(self.course.condition_met_as_prerequisite(student, 1))

        baker.make(CourseStudent, user=student, course=self.course, semester=SiteConfig.get().active_semester)
        self.assertTrue(self.course.condition_met_as_prerequisite(student, 1))

    def test_default_object_created(self):
        """ A data migration should make a default object for this model """
        self.assertTrue(Course.objects.filter(title="Default").exists())


class CourseStudentModelTest(TenantTestCase):

    def setUp(self):
        self.student = baker.make(User)
        self.course = baker.make(Course)
        self.course_student = baker.make(CourseStudent, user=self.student, course=self.course, semester=SiteConfig.get().active_semester)

    def test_course_student_creation(self):
        self.assertIsInstance(self.course_student, CourseStudent)
        # self.assertEqual(str(self.course), self.course.title)

    # def test_course_student_get_absolute_url(self):
    #     self.assertEqual(self.course_student.get_absolute_url(), reverse('courses:list'))

    @ patch('courses.models.Semester.fraction_complete')
    def test_calc_mark(self, fraction_complete):
        fraction_complete.return_value = 0.5
        course = baker.make(Course, xp_for_100_percent=100)
        course_student = baker.make(CourseStudent, user=self.student, course=course, semester=SiteConfig.get().active_semester)
        mark = course_student.calc_mark(50)
        self.assertEqual(mark, 100)
        mark = course_student.calc_mark(10)
        self.assertEqual(mark, 20)
        mark = course_student.calc_mark(0)
        self.assertEqual(mark, 0)

        fraction_complete.return_value = 1.0
        mark = course_student.calc_mark(100)
        self.assertEqual(mark, 100)
        mark = course_student.calc_mark(50)
        self.assertEqual(mark, 50)

    @ patch('courses.models.Semester.days_so_far')
    def test_xp_per_day_ave(self, days_so_far):

        self.student.profile.xp_cached = 120
        self.student.profile.save()
        days_so_far.return_value = 10
        xp_per_day = self.course_student.xp_per_day_ave()
        self.assertEqual(xp_per_day, 12)

        days_so_far.return_value = 0
        xp_per_day = self.course_student.xp_per_day_ave()
        self.assertEqual(xp_per_day, 0)


class BlockModelTest(TenantTestCase):

    def test_default_object_created(self):
        """ A data migration should make a default block """
        self.assertTrue(Block.objects.filter(block="Default").exists())


class RankManagerTest(TenantTestCase):

    def setUp(self):
        pass

    def test_get_rank_0XP(self):
        """ There is a default rank at 0 XP, and the site doesn't break if that rank is missing """
        rank_0 = Rank.objects.get_rank(0)
        self.assertIsNotNone(rank_0)

        # rank_0.delete()
        # rank_0 = Rank.objects.get_rank(0)
        # self.assertIsNotNone(rank_0)


class RankModelTest(TenantTestCase):

    def test_default_object_created(self):
        """ A data migration should make default objects for this model """
        self.assertTrue(Rank.objects.filter(name="Digital Noob").exists())
        self.assertEqual(Rank.objects.count(), 13)


class GradeModelTest(TenantTestCase):

    def test_default_object_created(self):
        """ A data migration should make default objects for this model """
        self.assertTrue(Grade.objects.filter(name="12").exists())
        self.assertEqual(Grade.objects.count(), 5)
