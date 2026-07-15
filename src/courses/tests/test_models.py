from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.db.models import ProtectedError

from freezegun import freeze_time
from unittest.mock import patch
from model_bakery import baker

from courses.models import Block, Course, CourseStudent, ExcludedDate, MarkRange, Rank, Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

User = get_user_model()


class MarkRangeModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.mr_50 = baker.make(MarkRange, minimum_mark=50.0)

    def test_mark_range_creation(self):
        self.assertIsInstance(self.mr_50, MarkRange)

    def test_mark_range__str__(self):
        expected_str = f"{self.mr_50.name} ({self.mr_50.minimum_mark}%)"
        self.assertEqual(str(self.mr_50), expected_str)


class MarkRangeManagerTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        # clear default mark range variables (every test in this class expects the defaults gone)
        MarkRange.objects.all().delete()

        cls.mr_50 = baker.make(MarkRange, minimum_mark=50.0)
        cls.mr_75 = baker.make(MarkRange, minimum_mark=75.0)

    def test_get_range(self):
        mr_100 = baker.make(MarkRange, minimum_mark=100.0)

        self.assertEqual(MarkRange.objects.get_range(25.0), None)
        self.assertEqual(MarkRange.objects.get_range(50.0), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(74.9), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(75.0), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0), mr_100)

    def test_get_range_with_course(self):
        c1 = baker.make(Course)
        c2 = baker.make(Course)
        mr_50_c1 = baker.make(MarkRange, minimum_mark=50.0, courses=[c1])
        mr_50_c2 = baker.make(MarkRange, minimum_mark=50.0, courses=[c2])
        mr_100_c1 = baker.make(MarkRange, minimum_mark=100.0, courses=[c1])

        self.assertEqual(MarkRange.objects.get_range(25.0), None)
        self.assertEqual(MarkRange.objects.get_range(50.0), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(50.0, [c1]), mr_50_c1)
        self.assertEqual(MarkRange.objects.get_range(74.9, [c2]), mr_50_c2)
        self.assertEqual(MarkRange.objects.get_range(74.9), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(75.0, [c1]), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(75.0), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0, [c2]), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0, [c1, c2]), mr_100_c1)

    def test_get_range_for_user(self):
        """ Test that `get_mark_range_for_user` returns the correct mark range for a given user.
        """
        user = baker.make(User)

        # A user with no courses should return None
        self.assertIsNone(MarkRange.objects.get_range_for_user(user))

        # Put the student in a course and test with various marks
        baker.make(CourseStudent, user=user, semester=SiteConfig.get().active_semester)

        with patch.object(user.profile, 'mark_cached', new=60.0):
            self.assertEqual(MarkRange.objects.get_range_for_user(user), self.mr_50)

        with patch.object(user.profile, 'mark_cached', new=80.0):
            self.assertEqual(MarkRange.objects.get_range_for_user(user), self.mr_75)

        with patch.object(user.profile, 'mark_cached', new=40.0):
            self.assertIsNone(MarkRange.objects.get_range_for_user(user))


class BlockModelManagerTest(ByteDeckTenantTestCase):

    def test_grouped_teachers_blocks_equals_one(self):
        """
            Should only return 1 group of teachers if regardless of the number of Blocks
        """

        teacher_owner = User.objects.get(username='owner')

        for _ in range(5):
            baker.make(Block, current_teacher=teacher_owner)

        group = Block.objects.grouped_teachers_blocks()

        self.assertEqual(len(group.keys()), 1)

    def test_grouped_teachers_blocks_more_than_one(self):
        """ Should return 3 group of teachers teaching Default, [AB] and [CD] blocks"""

        teacher_owner = User.objects.get(username='owner')
        teacher1 = baker.make(User, username='teacher1', is_staff=True)
        teacher2 = baker.make(User, username='teacher2', is_staff=True)

        block_default = Block.objects.get(name='Default')
        block_a = baker.make(Block, name='A', current_teacher=teacher1)
        block_b = baker.make(Block, name='B', current_teacher=teacher1)
        block_c = baker.make(Block, name='C', current_teacher=teacher2)
        block_d = baker.make(Block, name='D', current_teacher=teacher2)

        group = Block.objects.grouped_teachers_blocks()

        # Should assert to 3 groups
        self.assertEqual(len(group.keys()), 3)

        # admin teaches default block
        self.assertListEqual(group[teacher_owner.id], [block_default.name])
        # teacher1 teaches A and B block
        self.assertListEqual(group[teacher1.id], [block_a.name, block_b.name])
        # teacher2 teaches C and D block
        self.assertListEqual(group[teacher2.id], [block_c.name, block_d.name])


class SemesterModelManagerTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.semester_start = date(2019, 9, 1)  # Sep 1st 2019
        cls.semester_end = date(2019, 9, 30)  # Sep 30th, 2019
        cls.semester1 = baker.make(Semester, first_day=cls.semester_start, last_day=cls.semester_end)

    def test_get_current(self):
        """ Get's the current semester as defined by SiteConfig """
        self.assertEqual(Semester.objects.get_current(), SiteConfig.get().active_semester)

    def test_get_current_as_queryset(self):
        """ Get's the current semester object in a quesryset  """
        self.assertQuerySetEqual(Semester.objects.get_current(as_queryset=True), [SiteConfig.get().active_semester])


class SemesterModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.semester_start = date(2019, 9, 1)  # Sep 1st 2019
        cls.semester_end = date(2019, 9, 30)  # Sep 30th, 2019
        cls.today_fake = date(2019, 9, 15)  # Sep 15 2019, some date in the semester
        cls.semester = baker.make(Semester,
                                  first_day=cls.semester_start,
                                  last_day=cls.semester_end
                                  )

    def test_semester_creation(self):
        self.assertIsInstance(self.semester, Semester)

    def test_str__name_set(self):
        """`str(semester)` returns the name when one is set."""
        semester = baker.make(Semester, name='Fall 2019', first_day=self.semester_start)
        self.assertEqual(str(semester), 'Fall 2019')

    def test_str__name_blank(self):
        """`str(semester)` falls back to the first day formatted as mmm-YYYY when name is blank."""
        self.assertEqual(str(self.semester), 'Sep-2019')

    def test_str__name_blank_and_first_day_none(self):
        """`str(semester)` doesn't crash when name is blank and first_day is None.
        Regression test for issue #912 where the semester list page raised
        `'NoneType' object has no attribute 'strftime'`.
        """
        semester = baker.make(Semester, name='', first_day=None, last_day=None)
        self.assertEqual(str(semester), f'Semester {semester.pk}')

    def test_num_days__dates_none(self):
        """`num_days()` returns 0 instead of crashing when the semester has no
        first or last day set. Regression test for issue #912 (the semester list
        page renders num_days for every semester).
        """
        semester = baker.make(Semester, name='', first_day=None, last_day=None)
        self.assertEqual(semester.num_days(), 0)
        self.assertEqual(semester.num_days(upto_today=True), 0)

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


class CourseModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.course = baker.make(Course)

    def test_course_creation(self):
        self.assertIsInstance(self.course, Course)
        self.assertEqual(str(self.course), self.course.title)

    def test_get_absolute_url(self):
        """All courses return the course list"""
        self.assertEqual(self.course.get_absolute_url(), reverse('courses:course_list'))

    def test_condition_met_as_prerequisite(self):
        """ If the user is CURRENTLY registered in this course, then condition is met """
        student = baker.make(User)
        baker.make(CourseStudent, user=student, course=self.course)
        self.assertFalse(self.course.condition_met_as_prerequisite(student, 1))

        baker.make(CourseStudent, user=student, course=self.course, semester=SiteConfig.get().active_semester)
        self.assertTrue(self.course.condition_met_as_prerequisite(student, 1))

    def test_model_protection(self):
        """
            Quick test to see if Course model deletion is prevented when trying to delete Course model programmatically

            Course deletion is only prevented when there are CourseStudent models linked via foreign key to the Course model
        """
        # make sure initial variables are inplace
        student = baker.make(User)
        course_student = baker.make(CourseStudent, user=student, course=self.course, semester=SiteConfig.get().active_semester)
        self.assertTrue(CourseStudent.objects.count(), 1)
        self.assertEqual(course_student.course, self.course)

        # see if models.PROTECT is in place
        self.assertRaises(ProtectedError, self.course.delete)


class CourseStudentManagerTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.student = baker.make(User, username='test_student')
        cls.course = baker.make(Course)
        cls.course_student = baker.make(CourseStudent, user=cls.student, course=cls.course, semester=SiteConfig.get().active_semester)

    def test_current_course(self):
        """ Currently returns the first course in the active semester, if there are more than one"""
        # Add a second course to the student during active semester (+ SetUp)
        sc2 = baker.make(CourseStudent, user=self.student, course=baker.make(Course), semester=SiteConfig.get().active_semester)
        # order doesn't matter here, as long as it's one fo the courses the student is currently registered in
        self.assertIn(CourseStudent.objects.current_course(self.student), [sc2, self.course_student])

    def test_all_for_user_semester(self):
        """ Test that method returns all CourseStudent objects for a given user and semester """
        semester_to_check = baker.make(Semester)

        # This should show up
        sc1 = baker.make(CourseStudent, user=self.student, course=baker.make(Course), semester=semester_to_check)
        # So should this
        sc2 = baker.make(CourseStudent, user=self.student, course=baker.make(Course), semester=semester_to_check)

        # This shouldn't show up, different user
        student2 = baker.make(User)
        baker.make(CourseStudent, user=student2, course=self.course, semester=semester_to_check)

        # This shouldn't show up, different semester
        baker.make(CourseStudent, user=self.student, course=baker.make(Course), semester=SiteConfig.get().active_semester)

        course_students = CourseStudent.objects.all_for_user_semester(self.student, semester_to_check)
        self.assertEqual(course_students.count(), 2)
        self.assertQuerySetEqual(course_students, [sc1, sc2], ordered=False)

    @patch('profile_manager.models.Profile.xp_per_course')
    def test_calc_semester_grades(self, xp_per_course):
        """Test that method loops through all students, deactivates the student course, and sets a final_xp value"""

        # second student in same course as setup
        student2 = baker.make(User)
        course_student2 = baker.make(CourseStudent, user=student2, course=self.course, semester=SiteConfig.get().active_semester)

        # 3rd student in different course
        student3 = baker.make(User)
        course2 = baker.make(Course)
        course_student3 = baker.make(CourseStudent, user=student3, course=course2, semester=SiteConfig.get().active_semester)

        xp_per_course.return_value = 500
        CourseStudent.objects.calc_semester_grades(Semester.objects.get_current())

        self.course_student.refresh_from_db()
        course_student2.refresh_from_db()
        course_student3.refresh_from_db()

        self.assertFalse(self.course_student.active)
        self.assertFalse(course_student2.active)
        self.assertFalse(course_student3.active)

        self.assertEqual(self.course_student.final_xp, 500)
        self.assertEqual(course_student2.final_xp, 500)
        self.assertEqual(course_student3.final_xp, 500)

    @patch('profile_manager.models.Profile.xp_per_course')
    def test_calc_semester_grades__student_with_negative_xp(self, xp_per_course):
        """Test that an assertion error is raised when there is a student with negative xp"""
        xp_per_course.return_value = -10
        self.assertRaises(ValueError, CourseStudent.objects.calc_semester_grades,
                          Semester.objects.get_current())

    def test_all_users_for_active_semester(self):

        # There should be 1 student in the active semester
        self.assertEqual(CourseStudent.objects.all_users_for_active_semester().count(), 1)

        # Makef the student inactiveo
        self.student.is_active = False
        self.student.save()

        self.assertEqual(CourseStudent.objects.all_users_for_active_semester(students_only=True).count(), 0)


class CourseStudentModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.student = baker.make(User)
        cls.course = baker.make(Course)
        cls.course_student = baker.make(CourseStudent, user=cls.student, course=cls.course, semester=SiteConfig.get().active_semester)

    def test_course_student_creation(self):
        self.assertIsInstance(self.course_student, CourseStudent)
        # self.assertEqual(str(self.course), self.course.title)

    # def test_course_student_get_absolute_url(self):
    #     self.assertEqual(self.course_student.get_absolute_url(), reverse('courses:list'))

    @patch('courses.models.Semester.fraction_complete')
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

    @patch('courses.models.Semester.fraction_complete')
    def test_calc_mark__no_course(self, fraction_complete):
        """ calc_mark() method should be able to handle a CourseStudent with a null course
        """
        fraction_complete.return_value = 0.5

        # course isn't specific so baker won't make it since null=True
        course_student = baker.make(CourseStudent, user=self.student, semester=SiteConfig.get().active_semester)
        # this shouldn't error: 'NoneType' object has no attribute 'xp_for_100_percent'
        course_student.calc_mark(50)

    @patch('courses.models.Semester.days_so_far')
    def test_xp_per_day_ave(self, days_so_far):

        self.student.profile.xp_cached = 120
        self.student.profile.save()
        days_so_far.return_value = 10
        xp_per_day = self.course_student.xp_per_day_ave()
        self.assertEqual(xp_per_day, 12)

        days_so_far.return_value = 0
        xp_per_day = self.course_student.xp_per_day_ave()
        self.assertEqual(xp_per_day, 0)


class BlockModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.student = baker.make(User)
        cls.block = baker.make(Block)

    def test_model_protection(self):
        """
            Quick test to see if Block model deletion is prevented when trying to delete Block model programmatically
            Block deletion is only prevented when there are CourseStudent models linked via foreign key to the Block model
        """
        # Setup

        course_student = baker.make(CourseStudent, user=self.student, block=self.block)
        self.assertTrue(CourseStudent.objects.count(), 1)
        self.assertEqual(self.block, course_student.block)

        # see if models.PROTECT is in place
        self.assertRaises(ProtectedError, self.block.delete)

    def test_condition_met_as_prerequisite(self):
        """ If the user is registered in a course in this block during the active semester, then condition is met
        Tests check condition on self.block for self.student """

        # Student is not registered in any courses, so condition not met:
        self.assertFalse(self.block.condition_met_as_prerequisite(self.student))

        # Register student in a course in a  DIFFERENT block, condition still not met for self.block
        baker.make(CourseStudent, user=self.student, block=baker.make(Block))
        self.assertFalse(self.block.condition_met_as_prerequisite(self.student))

        # Register student in a course in self.block, but not the active semester, condition still not met for self.block
        baker.make(CourseStudent, user=self.student, block=self.block, semester=baker.make(Semester))
        self.assertFalse(self.block.condition_met_as_prerequisite(self.student))

        # Finally, register student in a course in self.block, and active semester, NOW condition is met for self.block
        baker.make(CourseStudent, user=self.student, block=self.block, semester=SiteConfig.get().active_semester)
        self.assertTrue(self.block.condition_met_as_prerequisite(self.student))


class RankManagerTest(ByteDeckTenantTestCase):

    def test_get_rank(self):
        """ Test that the correct rank is returned for a given XP value"""

        # default ranks are create from 0-1000XP, so test above that range.
        rank_2000 = baker.make(Rank, xp=2000)
        rank_3000 = baker.make(Rank, xp=3000)
        self.assertNotEqual(rank_2000, Rank.objects.get_rank(1999))
        self.assertEqual(rank_2000, Rank.objects.get_rank(2000))
        self.assertEqual(rank_2000, Rank.objects.get_rank(2001))
        self.assertEqual(rank_3000, Rank.objects.get_rank(3000))
        self.assertEqual(rank_3000, Rank.objects.get_rank(3001))

    def test_get_rank__0XP_and_deleted(self):
        """ There is a default rank at 0 XP, and the site doesn't break if that rank is missing """
        rank_0 = Rank.objects.get_rank(0)
        self.assertIsNotNone(rank_0)

        rank_0.delete()
        rank_0 = Rank.objects.get_rank(0)
        self.assertIsNotNone(rank_0)

    def test_get_rank__negative_XP(self):
        """ If a user has negative XP, they should still be assigned the lowest rank """
        rank_0 = Rank.objects.get_rank(-100)
        self.assertIsNotNone(rank_0)

    def test_get_next_rank(self):
        """ Test that the correct rank is returned for a given XP value"""

        # default ranks are create from 0-1000XP, so test above that range.
        rank_2000 = baker.make(Rank, xp=2000)
        rank_3000 = baker.make(Rank, xp=3000)
        self.assertEqual(rank_2000, Rank.objects.get_next_rank(1999))
        self.assertEqual(rank_3000, Rank.objects.get_next_rank(2000))
        self.assertEqual(rank_3000, Rank.objects.get_next_rank(2999))
        self.assertEqual(None, Rank.objects.get_next_rank(3000))

    def test_get_next_rank__when_deleted(self):
        """Method can handle if ranks were deleted """
        Rank.objects.all().delete()
        rank_1000 = Rank.objects.get_next_rank(1000)
        self.assertIsNone(rank_1000)


class RankModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        # every test in this class expects the default ranks gone, with only TestRank remaining
        Rank.objects.all().delete()
        cls.rank = baker.make(Rank, name="TestRank", xp=0)

    def test_rank_creation(self):
        self.assertIsInstance(self.rank, Rank)
        self.assertEqual(str(self.rank), self.rank.name)

    def test_get_absolute_url(self):
        """Absolute url for all ranks is the ranks list page"""
        self.assertEqual(self.rank.get_absolute_url(), reverse('courses:ranks'))

    def test_get_icon_url(self):
        """Returns the icon url for the rank, if no url then returns the default icon from SiteConfig"""
        self.assertEqual(self.rank.get_icon_url(), SiteConfig.get().get_default_icon_url())
        self.rank.icon = 'test.png'
        self.rank.save()

        self.assertEqual(self.rank.get_icon_url(), self.rank.icon.url)


class RankCacheInvalidationTest(ByteDeckTenantTestCase):
    """get_rank()/get_next_rank() read from the cached rank list, so every ORM
    write path must invalidate it: save/create and deletes are covered by the
    post_save/post_delete signals, while update()/bulk_create()/bulk_update()
    (which fire no signals) are covered by the RankQuerySet overrides.
    A stale cache would silently corrupt rank display everywhere."""

    def setUp(self):
        """Start each test with a cold rank cache."""
        from django.core.cache import cache
        cache.delete(Rank.objects.ranks_cache_key())

    def assert_cache_matches_db(self):
        """Assert the cached rank list matches the ranks table, comparing (pk, xp) in xp order."""
        cached = [(r.pk, r.xp) for r in Rank.objects.get_ranks_cached()]
        db = [(r.pk, r.xp) for r in Rank.objects.all().order_by('xp')]
        self.assertEqual(cached, db)

    def warm_cache(self):
        """Populate the rank cache so the test's write can be shown to invalidate it."""
        Rank.objects.get_ranks_cached()

    def test_cached_rank_lookups_hit_no_queries(self):
        """With a warm cache, get_rank() and get_next_rank() must not query the database."""
        self.warm_cache()
        with self.assertNumQueries(0):
            Rank.objects.get_rank(100)
            Rank.objects.get_next_rank(100)

    def test_save_invalidates_cache(self):
        """Creating a Rank (via save) and re-saving it must invalidate the cache (post_save signal)."""
        self.warm_cache()
        rank = baker.make(Rank, xp=123456)
        self.assertEqual(Rank.objects.get_rank(123456).pk, rank.pk)
        self.assert_cache_matches_db()

        rank.xp = 654321
        rank.save()
        self.assert_cache_matches_db()

    def test_instance_delete_invalidates_cache(self):
        """Deleting a Rank instance must invalidate the cache (post_delete signal)."""
        rank = baker.make(Rank, xp=123456)
        self.warm_cache()
        rank.delete()
        self.assert_cache_matches_db()

    def test_queryset_delete_invalidates_cache(self):
        """Queryset .delete() must invalidate the cache (receivers disable fast-delete, so post_delete fires)."""
        rank = baker.make(Rank, xp=123456)
        self.warm_cache()
        Rank.objects.filter(pk=rank.pk).delete()
        self.assert_cache_matches_db()

    def test_queryset_update_invalidates_cache(self):
        """Queryset .update() fires no signals; the RankQuerySet.update override must invalidate the cache."""
        rank = baker.make(Rank, xp=123456)
        self.warm_cache()
        Rank.objects.filter(pk=rank.pk).update(xp=654321)
        self.assertEqual(Rank.objects.get_rank(654321).pk, rank.pk)
        self.assert_cache_matches_db()

    def test_bulk_create_invalidates_cache(self):
        """bulk_create() fires no signals; the RankQuerySet.bulk_create override must invalidate the cache."""
        self.warm_cache()
        Rank.objects.bulk_create([Rank(name='Bulk Rank', xp=123456)])
        self.assert_cache_matches_db()

    def test_bulk_update_invalidates_cache(self):
        """bulk_update() fires no signals; the RankQuerySet.bulk_update override must invalidate the cache."""
        rank = baker.make(Rank, xp=123456)
        self.warm_cache()
        rank.xp = 654321
        Rank.objects.bulk_update([rank], ['xp'])
        self.assert_cache_matches_db()
