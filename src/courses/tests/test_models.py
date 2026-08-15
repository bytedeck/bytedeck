from datetime import date, datetime, timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from django.db.models import ProtectedError

from django_tenants.utils import get_public_schema_name
from freezegun import freeze_time
from unittest.mock import patch
from model_bakery import baker

from courses.models import Block, Course, CourseStudent, ExcludedDate, Grade, MarkRange, Rank, Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


class MarkRangeModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a MarkRange with a 50% minimum for the class tests."""
        cls.mr_50 = baker.make(MarkRange, minimum_mark=50.0)

    def test_mark_range__creation(self):
        """A MarkRange is created as the expected model instance."""
        self.assertIsInstance(self.mr_50, MarkRange)

    def test_mark_range__str__(self):
        """str(MarkRange) is the name followed by its minimum mark percentage."""
        expected_str = f"{self.mr_50.name} ({self.mr_50.minimum_mark}%)"
        self.assertEqual(str(self.mr_50), expected_str)


class MarkRangeManagerTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Clear the default mark ranges and create ranges at 50% and 75% minimums."""
        # clear default mark range variables (every test in this class expects the defaults gone)
        MarkRange.objects.all().delete()

        cls.mr_50 = baker.make(MarkRange, minimum_mark=50.0)
        cls.mr_75 = baker.make(MarkRange, minimum_mark=75.0)

    def test_get_range__by_mark(self):
        """get_range() returns the highest range whose minimum the mark meets."""
        mr_100 = baker.make(MarkRange, minimum_mark=100.0)

        self.assertIsNone(MarkRange.objects.get_range(25.0))
        self.assertEqual(MarkRange.objects.get_range(50.0), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(74.9), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(75.0), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0), mr_100)

    def test_get_range__with_course(self):
        """get_range() honours course-specific ranges when courses are passed."""
        c1 = baker.make(Course)
        c2 = baker.make(Course)
        mr_50_c1 = baker.make(MarkRange, minimum_mark=50.0, courses=[c1])
        mr_50_c2 = baker.make(MarkRange, minimum_mark=50.0, courses=[c2])
        mr_100_c1 = baker.make(MarkRange, minimum_mark=100.0, courses=[c1])

        self.assertIsNone(MarkRange.objects.get_range(25.0))
        self.assertEqual(MarkRange.objects.get_range(50.0), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(50.0, [c1]), mr_50_c1)
        self.assertEqual(MarkRange.objects.get_range(74.9, [c2]), mr_50_c2)
        self.assertEqual(MarkRange.objects.get_range(74.9), self.mr_50)
        self.assertEqual(MarkRange.objects.get_range(75.0, [c1]), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(75.0), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0, [c2]), self.mr_75)
        self.assertEqual(MarkRange.objects.get_range(101.0, [c1, c2]), mr_100_c1)

    def test_get_range_for_user__by_cached_mark(self):
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

    def test_grouped_teachers_blocks__single_teacher(self):
        """
            Should only return 1 group of teachers regardless of the number of Blocks
        """

        teacher_owner = User.objects.get(username='owner')

        for _ in range(5):
            baker.make(Block, current_teacher=teacher_owner)

        group = Block.objects.grouped_teachers_blocks()

        self.assertEqual(len(group.keys()), 1)

    def test_grouped_teachers_blocks__multiple_teachers(self):
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
        """Create a September 2019 semester for the manager tests."""
        cls.semester_start = date(2019, 9, 1)  # Sep 1st 2019
        cls.semester_end = date(2019, 9, 30)  # Sep 30th, 2019
        cls.semester1 = baker.make(Semester, first_day=cls.semester_start, last_day=cls.semester_end)

    def test_get_current__returns_active_semester(self):
        """ Gets the current semester as defined by SiteConfig """
        self.assertEqual(Semester.objects.get_current(), SiteConfig.get().active_semester)

    def test_get_current__as_queryset(self):
        """ Gets the current semester object in a queryset  """
        self.assertQuerySetEqual(Semester.objects.get_current(as_queryset=True), [SiteConfig.get().active_semester])

    def test_complete_semester__returns_sentinel_when_pointed_at_archived_semester(self):
        """A config left pointing at an archived semester has nothing to archive either."""
        active_sem = Semester.objects.get_current()
        active_sem.status = Semester.Status.ARCHIVED
        active_sem.save()

        self.assertEqual(Semester.objects.complete_semester(), Semester.NO_OPEN_SEMESTER)

    def test_complete_semester__returns_sentinel_when_no_semester_is_open(self):
        """With no active semester (the state archiving leaves behind), there is nothing to
        archive and the sentinel comes back instead of an error."""
        config = SiteConfig.get()
        config.active_semester = None
        config.save()

        self.assertEqual(Semester.objects.complete_semester(), Semester.NO_OPEN_SEMESTER)

    def test_complete_semester__leaves_the_deck_with_no_open_semester(self):
        """Archiving clears the active semester, so the deck sits between semesters
        (issue #1177) instead of pointing at an archived one."""
        archived = Semester.objects.complete_semester()

        self.assertTrue(archived.is_archived)
        self.assertIsNone(SiteConfig.get().active_semester)
        self.assertTrue(SiteConfig.get().has_no_open_semester())

    def test_complete_semester__leaves_the_other_open_semester_alone(self):
        """Archiving one semester is scoped to it (issue #2157 Phase 3): the other cohort's
        registrations stay active, their in-progress quests survive, and the deck's pointer
        is left alone because it named the semester still running."""
        config = SiteConfig.get()
        archiving = config.active_semester
        keeping = baker.make(Semester, status=Semester.Status.OPEN)
        config.active_semester = keeping
        config.save()

        student_here = baker.make(User)
        baker.make(CourseStudent, user=student_here, course=baker.make(Course), semester=archiving)
        student_there = baker.make(User)
        registration_there = baker.make(CourseStudent, user=student_there, course=baker.make(Course), semester=keeping)
        in_progress_there = baker.make(QuestSubmission, user=student_there, semester=keeping, is_completed=False)

        self.assertEqual(Semester.objects.complete_semester(archiving), archiving)

        keeping.refresh_from_db()
        self.assertTrue(keeping.is_open)
        registration_there.refresh_from_db()
        self.assertTrue(registration_there.active)  # their seat is not freed
        self.assertTrue(QuestSubmission.objects.filter(pk=in_progress_there.pk).exists())
        self.assertEqual(SiteConfig.get().active_semester, keeping)

    def test_complete_semester__is_not_blocked_by_another_semesters_approvals(self):
        """Quests awaiting approval in the other open semester are that semester's business,
        so they don't stand in the way of archiving this one."""
        archiving = SiteConfig.get().active_semester
        other = baker.make(Semester, status=Semester.Status.OPEN)
        baker.make(QuestSubmission, semester=other, is_completed=True, is_approved=False)

        self.assertEqual(Semester.objects.complete_semester(archiving), archiving)

    def test_complete_semester__returns_awaiting_approval_with_pending_submissions(self):
        """A semester can't be closed while quests are still awaiting approval."""
        baker.make(
            QuestSubmission,
            is_completed=True,
            is_approved=False,
            semester=SiteConfig.get().active_semester,
        )
        self.assertEqual(Semester.objects.complete_semester(), Semester.QUEST_AWAITING_APPROVAL)

    def test_complete_semester__clamp_records_negative_xp_as_zero(self):
        """With clamp_negative_xp on (the deck-suspension auto-close, #1734 B2), a
        student's negative balance is recorded as zero final XP and the semester
        closes; without it the STUDENTS_WITH_NEGATIVE_XP refusal stands."""
        User = get_user_model()
        baker.make(User, is_staff=True)  # a teacher must exist before students
        student = baker.make(User)
        registration = baker.make(CourseStudent, user=student, semester=SiteConfig.get().active_semester)

        with patch('profile_manager.models.Profile.xp_per_course', return_value=-50):
            self.assertEqual(Semester.objects.complete_semester(), Semester.STUDENTS_WITH_NEGATIVE_XP)
            result = Semester.objects.complete_semester(clamp_negative_xp=True)

        self.assertTrue(result.is_archived)
        registration.refresh_from_db()
        self.assertEqual(registration.final_xp, 0)
        self.assertFalse(registration.active)


    def test_calc_semester_grades__refusal_rolls_back_all_registrations(self):
        """A negative-XP refusal (clamp off) rolls back every registration
        deactivated earlier in the same call: no student is left deactivated
        while the semester stays open."""
        User = get_user_model()
        baker.make(User, is_staff=True)  # a teacher must exist before students
        students = [baker.make(User) for _ in range(2)]
        for student in students:
            baker.make(CourseStudent, user=student, semester=SiteConfig.get().active_semester, active=True)

        with patch('profile_manager.models.Profile.xp_per_course', side_effect=[10, -50, 10, -50]):
            with self.assertRaises(ValueError):
                CourseStudent.objects.calc_semester_grades(SiteConfig.get().active_semester)

        self.assertFalse(
            CourseStudent.objects.filter(semester=SiteConfig.get().active_semester, active=False).exists())

    def test_complete_semester__rolls_back_grades_when_a_student_has_negative_xp(self):
        """A negative-XP student aborts the close atomically: registrations finalized before
        the bad student was reached are rolled back and the semester stays open. Regression
        test for the pre-transaction behavior, where those students kept their recorded
        final_xp and active=False while the close itself failed."""
        active_semester = SiteConfig.get().active_semester
        course = baker.make(Course)

        # calc_semester_grades() processes registrations in block-name order (CourseStudent
        # Meta.ordering follows Block.Meta.ordering = ['name']), so the fine student in
        # block "A" is finalized before the negative-XP student in block "B" raises.
        fine_registration = baker.make(
            CourseStudent, user=baker.make(User), course=course,
            block=baker.make(Block, name='A'), semester=active_semester,
        )
        baker.make(
            CourseStudent, user=baker.make(User), course=course,
            block=baker.make(Block, name='B'), semester=active_semester,
            xp_adjustment=-10,  # makes this student's XP negative
        )

        self.assertEqual(Semester.objects.complete_semester(), Semester.STUDENTS_WITH_NEGATIVE_XP)

        # the fine student's registration must be untouched, and the semester still open
        fine_registration.refresh_from_db()
        self.assertTrue(fine_registration.active)
        self.assertIsNone(fine_registration.final_xp)
        active_semester.refresh_from_db()
        self.assertFalse(active_semester.is_archived)


class SemesterModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a September 2019 semester used across the semester model tests."""
        cls.semester_start = date(2019, 9, 1)  # Sep 1st 2019
        cls.semester_end = date(2019, 9, 30)  # Sep 30th, 2019
        cls.today_fake = date(2019, 9, 15)  # Sep 15 2019, some date in the semester
        cls.semester = baker.make(Semester,
                                  first_day=cls.semester_start,
                                  last_day=cls.semester_end
                                  )

    def test_semester__creation(self):
        """A Semester is created as the expected model instance."""
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

    def test_is_within_dates__within_and_outside_dates(self):
        """is_within_dates() is True on and between the first and last day, and False outside them."""
        # before semester starts: False
        before_start = self.semester_start - timedelta(days=1)
        with freeze_time(before_start, tz_offset=0):
            self.assertFalse(self.semester.is_within_dates())

        # after semester ends: False
        after_end = self.semester_end + timedelta(days=1)
        with freeze_time(after_end, tz_offset=0):
            self.assertFalse(self.semester.is_within_dates())

        # during semester: True
        during = self.semester_start + timedelta(days=1)
        with freeze_time(during, tz_offset=0):
            self.assertTrue(self.semester.is_within_dates())

        # first day: True
        with freeze_time(self.semester_start, tz_offset=0):
            self.assertTrue(self.semester.is_within_dates())
        # last day: True
        with freeze_time(self.semester_end, tz_offset=0):
            self.assertTrue(self.semester.is_within_dates())

        # Timezone problems?

    def test_has_ended__only_after_last_day(self):
        """has_ended() is True only once the last day is in the past, and False when the
        semester has no last day at all."""
        with freeze_time(self.semester_end, tz_offset=0):
            self.assertFalse(self.semester.has_ended())

        with freeze_time(self.semester_end + timedelta(days=1), tz_offset=0):
            self.assertTrue(self.semester.has_ended())

        dateless_semester = baker.make(Semester, name='dateless', first_day=None, last_day=None)
        self.assertFalse(dateless_semester.has_ended())

    def test_status_properties__match_the_lifecycle_stage(self):
        """Exactly one of is_upcoming/is_open/is_archived is True at each stage of the
        lifecycle, and a semester defaults to upcoming until it is started."""
        semester = baker.make(Semester)
        self.assertEqual(
            (semester.is_upcoming, semester.is_open, semester.is_archived), (True, False, False)
        )

        semester.status = Semester.Status.OPEN
        self.assertEqual(
            (semester.is_upcoming, semester.is_open, semester.is_archived), (False, True, False)
        )

        semester.status = Semester.Status.ARCHIVED
        self.assertEqual(
            (semester.is_upcoming, semester.is_open, semester.is_archived), (False, False, True)
        )

    def test_status_properties__is_open_ignores_the_dates(self):
        """is_open is the lifecycle status, not a date check: a semester whose last day has
        passed stays open until it is archived (that gap is what has_ended() flags)."""
        ended = baker.make(
            Semester, status=Semester.Status.OPEN,
            first_day=date.today() - timedelta(days=100), last_day=date.today() - timedelta(days=10),
        )

        self.assertTrue(ended.is_open)
        self.assertFalse(ended.is_within_dates())
        self.assertTrue(ended.has_ended())

    def test_queryset_helpers__filter_by_lifecycle_stage(self):
        """The queryset helpers select semesters by lifecycle stage."""
        upcoming = baker.make(Semester, status=Semester.Status.UPCOMING)
        open_semester = baker.make(Semester, status=Semester.Status.OPEN)
        archived = baker.make(Semester, status=Semester.Status.ARCHIVED)

        self.assertIn(upcoming, Semester.objects.upcoming())
        self.assertIn(open_semester, Semester.objects.open())
        self.assertIn(archived, Semester.objects.archived())
        self.assertNotIn(archived, Semester.objects.open())
        self.assertNotIn(upcoming, Semester.objects.archived())

    def test_num_days__excludes_weekends_and_excluded_dates(self):
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

    def test_num_days__upto_today(self):
        """The number of classes in the semester SO FAR up to today
        """
        with freeze_time(date(2019, 9, 15), tz_offset=0):
            self.assertEqual(self.semester.num_days(upto_today=True), 10)

        # Future dates should only go up to end.
        with freeze_time(date(2019, 10, 15), tz_offset=0):
            self.assertEqual(self.semester.num_days(upto_today=True), 21)

    def test_excluded_days__returns_excluded_dates(self):
        """ returns a list of dates excluded for this semester (holidays and other non-instructional days) """
        # add some excluded dates
        baker.make(ExcludedDate, semester=self.semester, date=date(2019, 9, 1))  # Sun, shouldn't count
        baker.make(ExcludedDate, semester=self.semester, date=date(2019, 9, 2))  # Mon

        dates = self.semester.excluded_days()
        self.assertListEqual(list(dates), [date(2019, 9, 1), date(2019, 9, 2)])

    def test_days_so_far__equals_num_days_upto_today(self):
        """days_so_far() equals num_days(upto_today=True)."""
        self.assertEqual(self.semester.days_so_far(), self.semester.num_days(upto_today=True))

    def test_fraction_complete__partway_through(self):
        """ how far through the semester as a fraction """
        with freeze_time(date(2019, 9, 15), tz_offset=0):
            # 10 days so far (excluding weekends) / 21 days total
            fraction_complete = self.semester.fraction_complete()
            self.assertAlmostEqual(fraction_complete, 10 / 21)

    def test_percent_complete__partway_through(self):
        """ how far through the semester as a percent """
        with freeze_time(date(2019, 9, 15), tz_offset=0):
            # 10 days so far (excluding weekends) / 21 days total * 100
            percent_complete = self.semester.percent_complete()
            self.assertAlmostEqual(percent_complete, 10 / 21 * 100)

    def test_get_interim1_date__quarter_point(self):
        """get_interim1_date() is the date a quarter of the way through the semester."""
        self.assertEqual(self.semester.get_interim1_date(), self.semester.get_date(0.25))

    def test_get_term_date__midpoint(self):
        """get_term_date() is the date halfway through the semester."""
        self.assertEqual(self.semester.get_term_date(), self.semester.get_date(0.5))

    def test_get_interim2_date__three_quarter_point(self):
        """get_interim2_date() is the date three quarters of the way through the semester."""
        self.assertEqual(self.semester.get_interim2_date(), self.semester.get_date(0.75))

    def test_get_final_date__last_day(self):
        """get_final_date() is the semester's last day."""
        self.assertEqual(self.semester.get_final_date(), self.semester.last_day)

    def test_get_date__rolls_back_off_weekends(self):
        """ Gets the closest date, rolling back if it falls on a weekend or excluded
        after a fraction of the semester is over """
        self.assertEqual(self.semester.get_date(0.25), date(2019, 9, 6))
        self.assertEqual(self.semester.get_date(0.5), date(2019, 9, 13))  # lands on a weekend so roll back to the friday
        self.assertEqual(self.semester.get_date(1.0), self.semester.last_day)

    def test_get_datetime_by_days_since_start__skips_weekends(self):
        """ 5 days since start of semester should fall on 6 Sep 2019,
        6 days should push through weekend and land on 9 Sep 2019 """
        dt = self.semester.get_datetime_by_days_since_start(5)
        expected = timezone.make_aware(datetime(2019, 9, 6, 23, 59, 59, 999999), timezone.get_default_timezone())
        self.assertEqual(dt, expected)

        dt = self.semester.get_datetime_by_days_since_start(6)
        expected = timezone.make_aware(datetime(2019, 9, 9, 23, 59, 59, 999999), timezone.get_default_timezone())
        self.assertEqual(dt, expected)

    def test_reset_students_xp_cached__zeroes_xp(self):
        """Students' xp_cached should be set to 0."""
        student = baker.make(User)
        course = baker.make(Course)
        active_semester = SiteConfig.get().active_semester

        student.profile.xp_cached = 100
        student.profile.save()

        baker.make(CourseStudent, user=student, course=course, semester=active_semester)

        active_semester.reset_students_xp_cached()
        self.assertEqual(student.profile.xp_cached, 0)


class NoOpenSemesterTest(ByteDeckTenantTestCase):
    """A deck between semesters, which is what archiving now leaves behind (issue #1177).

    Nothing is open, so everything scoped to the deck's semester is empty rather than
    broken, and registrations from the semester that was archived count as past.
    """

    def setUp(self):
        """Register a student, then archive the semester so the deck has none open."""
        self.student = baker.make(User)
        self.registration = baker.make(
            CourseStudent, user=self.student, course=baker.make(Course),
            semester=SiteConfig.get().active_semester,
        )
        self.archived_semester = Semester.objects.complete_semester()

    def test_archiving__leaves_no_active_semester(self):
        """The state under test: the semester is archived and nothing is pointed at."""
        self.assertTrue(self.archived_semester.is_archived)
        self.assertIsNone(SiteConfig.get().active_semester)

    def test_get_current__returns_nothing(self):
        """There is no current semester, and the queryset form is empty (not one row of None)."""
        self.assertIsNone(Semester.objects.get_current())
        self.assertFalse(Semester.objects.get_current(as_queryset=True).exists())

    def test_get_current__ignores_a_pointer_at_a_semester_that_is_not_open(self):
        """A config pointing at an upcoming semester still means no current semester: the
        pointer alone doesn't make a semester the one students are in, and the deck must
        agree with has_no_open_semester() about that."""
        config = SiteConfig.get()
        config.active_semester = baker.make(Semester, status=Semester.Status.UPCOMING)
        config.save()

        self.assertTrue(SiteConfig.get().has_no_open_semester())
        self.assertIsNone(Semester.objects.get_current())
        self.assertFalse(Semester.objects.get_current(as_queryset=True).exists())

    def test_complete_semester__will_not_archive_a_semester_that_is_not_open(self):
        """An upcoming semester has no final marks to record, so archiving refuses rather
        than skipping it straight to the terminal stage."""
        upcoming = baker.make(Semester, status=Semester.Status.UPCOMING)
        config = SiteConfig.get()
        config.active_semester = upcoming
        config.save()

        self.assertEqual(Semester.objects.complete_semester(), Semester.NO_OPEN_SEMESTER)
        upcoming.refresh_from_db()
        self.assertTrue(upcoming.is_upcoming)

    def test_current_courses__is_empty(self):
        """Nobody is registered in a current course, so a student has none."""
        self.assertFalse(CourseStudent.objects.current_courses(self.student).exists())
        self.assertIsNone(CourseStudent.objects.current_course(self.student))

    def test_all_users_in_open_semesters__is_empty(self):
        """No user is in the active semester, so staff lists and task recipients come back
        empty instead of picking up registrations whose semester was deleted."""
        orphaned = baker.make(CourseStudent, user=baker.make(User), semester=None)

        users = CourseStudent.objects.all_users_in_open_semesters()

        self.assertFalse(users.exists())
        self.assertNotIn(orphaned.user, users)

    def test_has_past_courses__counts_every_registration(self):
        """With none open, every registration the student has is in a past semester."""
        self.assertTrue(self.student.profile.has_past_courses)

    def test_reset_students_xp_cached__still_zeroes_the_archived_semesters_students(self):
        """Archiving clears the active semester pointer, so the XP reset works off the
        semester's own registrations: its students' cached XP still gets zeroed."""
        self.student.profile.xp_cached = 100
        self.student.profile.save()

        self.archived_semester.reset_students_xp_cached()

        self.student.profile.refresh_from_db()
        self.assertEqual(self.student.profile.xp_cached, 0)


class StudentOwnSemesterTest(ByteDeckTenantTestCase):
    """A student's semester comes from their own registration, not from the deck's pointer
    (issue #2157 Phase 3, the inversion #1781 needs).

    The deck can only name one semester, so once several are open it can't say which one a
    given student earns XP in. Their registration can, and these tests pin that: the
    second open semester here is built directly, since starting a semester the normal way
    still leaves only one open until concurrent semesters land.
    """

    @classmethod
    def setUpTestData(cls):
        """A student registered in the deck's open semester, plus a second open semester
        with its own student, and a teacher registered in neither."""
        cls.deck_semester = SiteConfig.get().active_semester
        cls.other_semester = baker.make(Semester, status=Semester.Status.OPEN)

        cls.student = baker.make(User, username='deck_semester_student')
        baker.make(CourseStudent, user=cls.student, course=baker.make(Course), semester=cls.deck_semester)

        cls.other_student = baker.make(User, username='other_semester_student')
        baker.make(CourseStudent, user=cls.other_student, course=baker.make(Course), semester=cls.other_semester)

        cls.teacher = baker.make(User, username='unregistered_teacher', is_staff=True)

    def test_current_semester__is_the_students_own_registration(self):
        """A student in the semester the deck points at gets that semester."""
        self.assertEqual(CourseStudent.objects.current_semester(self.student), self.deck_semester)

    def test_current_semester__ignores_the_deck_pointer(self):
        """A student registered in a different open semester gets theirs, not the deck's.
        This is the whole point of reading the registration: the deck still points at
        deck_semester, and for this student that answer is wrong."""
        self.assertEqual(SiteConfig.get().open_semester, self.deck_semester)
        self.assertEqual(CourseStudent.objects.current_semester(self.other_student), self.other_semester)

    def test_current_semester__unregistered_user_falls_back_to_the_deck(self):
        """Someone with no registration (a teacher trying a quest, a student who hasn't
        joined a course) keeps earning XP in the deck's open semester, as before."""
        self.assertEqual(CourseStudent.objects.current_semester(self.teacher), self.deck_semester)

    def test_current_semester__unregistered_user_between_semesters_is_none(self):
        """With nothing open and no registration to fall back on, there is no semester."""
        Semester.objects.filter(pk=self.other_semester.pk).update(status=Semester.Status.ARCHIVED)
        Semester.objects.complete_semester()
        self.assertIsNone(CourseStudent.objects.current_semester(self.teacher))

    def test_current_semester__archived_registration_is_not_current(self):
        """Archiving the semester a student was in leaves them with no current registration.
        They fall back to the deck's pointer, which archiving cleared, rather than staying
        attached to the archived semester (or being adopted by someone else's open one)."""
        Semester.objects.complete_semester()
        self.other_semester.refresh_from_db()
        self.assertTrue(self.other_semester.is_open)
        self.assertIsNone(CourseStudent.objects.current_semester(self.student))

    def test_xp_totals__count_what_was_earned_in_the_students_own_semester(self):
        """The end-to-end pairing of stamping and reading. A quest approved and a badge
        granted for a student in the semester the deck does not point at are stamped with
        their semester, and their XP total then counts both. Reading through the deck's
        semester instead would leave the student looking at zero XP they can't explain."""
        from badges.models import Badge, BadgeAssertion

        quest = baker.make(Quest, xp=25, published=True)
        submission = QuestSubmission.objects.create_submission(self.other_student, quest)
        submission.mark_completed()
        submission.mark_approved()
        BadgeAssertion.objects.create_assertion(self.other_student, baker.make(Badge, xp=10))

        self.assertEqual(submission.semester, self.other_semester)
        self.assertEqual(self.other_student.profile.xp_invalidate_cache(), 35)

    def test_xp_totals__ignore_xp_earned_in_a_different_semester(self):
        """XP stays scoped: a submission stamped with someone else's open semester is not
        added to this student's total just because both semesters are open."""
        from badges.models import Badge, BadgeAssertion

        baker.make(
            QuestSubmission, user=self.other_student, quest__xp=100, semester=self.deck_semester,
            is_completed=True, is_approved=True,
        )
        BadgeAssertion.objects.create_assertion(
            self.other_student, baker.make(Badge, xp=50), active_semester=self.deck_semester.pk,
        )

        self.assertEqual(self.other_student.profile.xp_invalidate_cache(), 0)

    def test_current_courses__covers_every_course_in_that_semester(self):
        """A student holds registrations in several courses and groups within their one
        semester, and all of them are current; registrations in another semester are not."""
        second_course = baker.make(CourseStudent, user=self.student, course=baker.make(Course), semester=self.deck_semester)
        baker.make(CourseStudent, user=self.student, course=baker.make(Course), semester=baker.make(Semester))

        current = CourseStudent.objects.current_courses(self.student)
        self.assertEqual(current.count(), 2)
        self.assertIn(second_course, current)


class CourseModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a Course for the class tests."""
        cls.course = baker.make(Course)

    def test_course__creation(self):
        """A Course is created and its str is its title."""
        self.assertIsInstance(self.course, Course)
        self.assertEqual(str(self.course), self.course.title)

    def test_get_absolute_url__returns_course_list(self):
        """All courses return the course list"""
        self.assertEqual(self.course.get_absolute_url(), reverse('courses:course_list'))

    def test_condition_met_as_prerequisite__currently_registered(self):
        """ If the user is CURRENTLY registered in this course, then condition is met """
        student = baker.make(User)
        baker.make(CourseStudent, user=student, course=self.course)
        self.assertFalse(self.course.condition_met_as_prerequisite(student, 1))

        baker.make(CourseStudent, user=student, course=self.course, semester=SiteConfig.get().active_semester)
        self.assertTrue(self.course.condition_met_as_prerequisite(student, 1))

    def test_model_protection__course_with_students(self):
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
        """Create a student registered in a course in the active semester."""
        cls.student = baker.make(User, username='test_student')
        cls.course = baker.make(Course)
        cls.course_student = baker.make(CourseStudent, user=cls.student, course=cls.course, semester=SiteConfig.get().active_semester)

    def test_current_course__returns_active_semester_course(self):
        """ Currently returns the first course in the active semester, if there are more than one"""
        # Add a second course to the student during active semester (+ SetUp)
        sc2 = baker.make(CourseStudent, user=self.student, course=baker.make(Course), semester=SiteConfig.get().active_semester)
        # order doesn't matter here, as long as it's one of the courses the student is currently registered in
        self.assertIn(CourseStudent.objects.current_course(self.student), [sc2, self.course_student])

    def test_all_for_user_semester__filters_by_user_and_semester(self):
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
    def test_calc_semester_grades__deactivates_and_sets_final_xp(self, xp_per_course):
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

    def test_all_users_in_open_semesters__is_empty_on_the_public_schema(self):
        """The public tenant has no courses tables, and this runs there while booting, so it
        returns an empty queryset rather than querying a table that isn't there."""
        with patch('courses.models.connection') as mock_connection:
            mock_connection.schema_name = get_public_schema_name()
            result = CourseStudent.objects.all_users_in_open_semesters()
        self.assertEqual(result.count(), 0)

    def test_all_users_in_open_semesters__excludes_inactive(self):
        """The deck's roster counts students in an open semester, leaving out inactive users."""
        # There should be 1 student in the open semester
        self.assertEqual(CourseStudent.objects.all_users_in_open_semesters().count(), 1)

        # Make the student inactive
        self.student.is_active = False
        self.student.save()

        self.assertEqual(CourseStudent.objects.all_users_in_open_semesters(students_only=True).count(), 0)

    def test_all_users_in_open_semesters__spans_every_open_semester(self):
        """Two cohorts on different calendars are both current, so the deck's roster is the
        union of them rather than whichever one the deck's pointer names (issue #2157 Phase 3)."""
        other_semester = baker.make(Semester, status=Semester.Status.OPEN)
        other_student = baker.make(User)
        baker.make(CourseStudent, user=other_student, course=baker.make(Course), semester=other_semester)

        users = CourseStudent.objects.all_users_in_open_semesters()

        self.assertIn(self.student, users)
        self.assertIn(other_student, users)

    def test_all_users_in_open_semesters__counts_a_student_in_two_courses_once(self):
        """A student registered in several courses within their semester is one user, not one
        per registration."""
        baker.make(CourseStudent, user=self.student, course=baker.make(Course), semester=SiteConfig.get().active_semester)

        self.assertEqual(CourseStudent.objects.all_users_in_open_semesters().count(), 1)

    def test_all_users_in_open_semesters__leaves_out_archived_semesters(self):
        """Archiving a semester takes its students off the roster: that is what frees seats."""
        Semester.objects.complete_semester()

        self.assertEqual(CourseStudent.objects.all_users_in_open_semesters().count(), 0)


class CourseStudentModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a student registered in a course in the active semester."""
        cls.student = baker.make(User)
        cls.course = baker.make(Course)
        cls.course_student = baker.make(CourseStudent, user=cls.student, course=cls.course, semester=SiteConfig.get().active_semester)

    def test_course_student__creation(self):
        """A CourseStudent is created as the expected model instance."""
        self.assertIsInstance(self.course_student, CourseStudent)

    def test_str__includes_username_semester_block_and_course(self):
        """A CourseStudent's string lists the student's username, semester, block and course."""
        block = baker.make(Block, name='B1')
        semester = SiteConfig.get().active_semester
        course = baker.make(Course, title='Math')
        course_student = baker.make(CourseStudent, user=self.student, course=course, block=block, semester=semester)

        result = str(course_student)

        self.assertIn(self.student.get_username(), result)
        self.assertIn(str(semester), result)
        self.assertIn('B1', result)
        self.assertIn(str(course), result)

    @patch('courses.models.Semester.fraction_complete')
    def test_calc_mark__scales_with_fraction_complete(self, fraction_complete):
        """calc_mark() scales a student's XP into a mark based on how far the semester has progressed."""
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
    def test_xp_per_day_ave__divides_xp_by_days(self, days_so_far):
        """xp_per_day_ave() is the student's cached XP divided by days so far, or 0 when no days."""
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
        """Create a student and a Block for the class tests."""
        cls.student = baker.make(User)
        cls.block = baker.make(Block)

    def test_model_protection__block_with_students(self):
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

    def test_condition_met_as_prerequisite__registered_in_block_active_semester(self):
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

    def test_get_rank__returns_rank_for_xp(self):
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

    def test_get_next_rank__returns_next_rank_for_xp(self):
        """ Test that the correct rank is returned for a given XP value"""

        # default ranks are create from 0-1000XP, so test above that range.
        rank_2000 = baker.make(Rank, xp=2000)
        rank_3000 = baker.make(Rank, xp=3000)
        self.assertEqual(rank_2000, Rank.objects.get_next_rank(1999))
        self.assertEqual(rank_3000, Rank.objects.get_next_rank(2000))
        self.assertEqual(rank_3000, Rank.objects.get_next_rank(2999))
        self.assertIsNone(Rank.objects.get_next_rank(3000))

    def test_get_next_rank__when_deleted(self):
        """Method can handle if ranks were deleted """
        Rank.objects.all().delete()
        rank_1000 = Rank.objects.get_next_rank(1000)
        self.assertIsNone(rank_1000)

    def test_get_ranks_lte__returns_ranks_at_or_below_xp(self):
        """get_ranks_lte(xp) returns the ranks whose xp is <= the given value."""
        Rank.objects.all().delete()
        rank_0 = baker.make(Rank, xp=0)
        rank_100 = baker.make(Rank, xp=100)
        baker.make(Rank, xp=200)

        result = Rank.objects.all().get_ranks_lte(100)

        self.assertCountEqual(result, [rank_0, rank_100])

    def test_get_ranks_gt__returns_ranks_above_xp(self):
        """get_ranks_gt(xp) returns the ranks whose xp is strictly greater than the given value."""
        Rank.objects.all().delete()
        baker.make(Rank, xp=0)
        baker.make(Rank, xp=100)
        rank_200 = baker.make(Rank, xp=200)

        result = Rank.objects.all().get_ranks_gt(100)

        self.assertCountEqual(result, [rank_200])


class RankModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Clear the default ranks and create a single TestRank at 0 XP."""
        # every test in this class expects the default ranks gone, with only TestRank remaining
        Rank.objects.all().delete()
        cls.rank = baker.make(Rank, name="TestRank", xp=0)

    def test_rank__creation(self):
        """A Rank is created and its str is its name."""
        self.assertIsInstance(self.rank, Rank)
        self.assertEqual(str(self.rank), self.rank.name)

    def test_get_absolute_url__returns_ranks_list(self):
        """Absolute url for all ranks is the ranks list page"""
        self.assertEqual(self.rank.get_absolute_url(), reverse('courses:ranks'))

    def test_get_icon_url__default_and_custom(self):
        """Returns the icon url for the rank, if no url then returns the default icon from SiteConfig"""
        self.assertEqual(self.rank.get_icon_url(), SiteConfig.get().get_default_icon_url())
        self.rank.icon = 'test.png'
        self.rank.save()

        self.assertEqual(self.rank.get_icon_url(), self.rank.icon.url)

    def test_get_map__falls_back_to_lookup_when_not_cached(self):
        """Without a pre-populated _map_cached, get_map() looks the map up individually
        (returning None when the rank has no map)."""
        self.assertFalse(hasattr(self.rank, '_map_cached'))
        self.assertIsNone(self.rank.get_map())


class GradeModelTest(ByteDeckTenantTestCase):
    """Tests for the Grade model (used as a prerequisite type)."""

    @classmethod
    def setUpTestData(cls):
        """Create a grade (with a value that won't collide with the default grades) and a student."""
        cls.grade = baker.make(Grade, name='Test Grade', value=99)
        cls.student = baker.make(User)

    def test_str__returns_name(self):
        """A grade's string representation is its name."""
        self.assertEqual(str(self.grade), 'Test Grade')

    def test_condition_met_as_prerequisite__true_when_student_registered_in_that_grade(self):
        """The grade prereq is met when the student has a current course tagged with that grade."""
        baker.make(
            CourseStudent,
            user=self.student,
            grade_fk=self.grade,
            semester=SiteConfig.get().active_semester,
        )
        self.assertTrue(self.grade.condition_met_as_prerequisite(self.student, 1))

    def test_condition_met_as_prerequisite__false_when_student_not_in_that_grade(self):
        """The grade prereq is not met when the student has no current course in that grade."""
        self.assertFalse(self.grade.condition_met_as_prerequisite(self.student, 1))


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

    def test_cached_rank_lookups__hit_no_queries(self):
        """With a warm cache, get_rank() and get_next_rank() must not query the database."""
        self.warm_cache()
        with self.assertNumQueries(0):
            Rank.objects.get_rank(100)
            Rank.objects.get_next_rank(100)

    def test_save__invalidates_cache(self):
        """Creating a Rank (via save) and re-saving it must invalidate the cache (post_save signal)."""
        self.warm_cache()
        rank = baker.make(Rank, xp=123456)
        self.assertEqual(Rank.objects.get_rank(123456).pk, rank.pk)
        self.assert_cache_matches_db()

        rank.xp = 654321
        rank.save()
        self.assert_cache_matches_db()

    def test_instance_delete__invalidates_cache(self):
        """Deleting a Rank instance must invalidate the cache (post_delete signal)."""
        rank = baker.make(Rank, xp=123456)
        self.warm_cache()
        rank.delete()
        self.assert_cache_matches_db()

    def test_queryset_delete__invalidates_cache(self):
        """Queryset .delete() must invalidate the cache (receivers disable fast-delete, so post_delete fires)."""
        rank = baker.make(Rank, xp=123456)
        self.warm_cache()
        Rank.objects.filter(pk=rank.pk).delete()
        self.assert_cache_matches_db()

    def test_queryset_update__invalidates_cache(self):
        """Queryset .update() fires no signals; the RankQuerySet.update override must invalidate the cache."""
        rank = baker.make(Rank, xp=123456)
        self.warm_cache()
        Rank.objects.filter(pk=rank.pk).update(xp=654321)
        self.assertEqual(Rank.objects.get_rank(654321).pk, rank.pk)
        self.assert_cache_matches_db()

    def test_bulk_create__invalidates_cache(self):
        """bulk_create() fires no signals; the RankQuerySet.bulk_create override must invalidate the cache."""
        self.warm_cache()
        Rank.objects.bulk_create([Rank(name='Bulk Rank', xp=123456)])
        self.assert_cache_matches_db()

    def test_bulk_update__invalidates_cache(self):
        """bulk_update() fires no signals; the RankQuerySet.bulk_update override must invalidate the cache."""
        rank = baker.make(Rank, xp=123456)
        self.warm_cache()
        rank.xp = 654321
        Rank.objects.bulk_update([rank], ['xp'])
        self.assert_cache_matches_db()


class ExcludedDateModelTest(ByteDeckTenantTestCase):
    """Tests for the ExcludedDate model (dates excluded from a semester's class-day count)."""

    def test_str__returns_date_formatted_dd_mon_yyyy(self):
        """An excluded date's string is its date formatted as DD-Mon-YYYY."""
        semester = baker.make(Semester)
        excluded = baker.make(ExcludedDate, semester=semester, date=date(2019, 9, 2))
        self.assertEqual(str(excluded), '02-Sep-2019')
