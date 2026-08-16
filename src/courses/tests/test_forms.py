import datetime

from django import forms
from django.contrib.auth import get_user_model
from django_select2.forms import Select2Widget
from model_bakery import baker

from badges.forms import BadgeAssertionForm
from courses.forms import CourseStudentForm, SemesterForm
from courses.models import Block, Course, CourseStudent, Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.forms import SubmissionQuickReplyFormStudent
from siteconfig.models import SiteConfig

User = get_user_model()


class CourseStudentFormTest(ByteDeckTenantTestCase):
    """Which semester a student registering for a course can join (issue #2157 Phase 3)."""

    def test_semester_field__offers_every_open_semester(self):
        """A deck can run course groups on different calendars (#1781), so registration offers
        every open semester and the student says which one they are joining, not just the one
        the deck's pointer names."""
        pointed_at = SiteConfig.get().active_semester
        other = baker.make(Semester, status=Semester.Status.OPEN)

        form = CourseStudentForm()

        self.assertEqual(list(form.fields['semester'].queryset), [pointed_at, other])

    def test_semester_field__defaults_to_the_decks_own_semester(self):
        """The choices are listed newest term first, so a deck running an older semester
        alongside a newer one would otherwise offer the newer one by default and quietly put
        students in the wrong cohort. The deck's own semester is preselected instead."""
        older = SiteConfig.get().active_semester
        baker.make(
            Semester, status=Semester.Status.OPEN,
            first_day=older.first_day + datetime.timedelta(days=200),
            last_day=older.last_day + datetime.timedelta(days=200),
        )

        form = CourseStudentForm()

        self.assertEqual(form.fields['semester'].initial, older.pk)
        self.assertEqual(form['semester'].value(), older.pk)

    def test_semester_field__an_existing_registration_keeps_its_own_semester(self):
        """Editing a registration shows the semester it is actually in, not the deck's default:
        a staff correction to the group must not silently move the student's term."""
        other_semester = baker.make(Semester, status=Semester.Status.OPEN)
        registration = baker.make(
            CourseStudent, user=baker.make(User), course=baker.make(Course),
            semester=other_semester, block=baker.make(Block),
        )

        form = CourseStudentForm(instance=registration)

        self.assertEqual(form['semester'].value(), other_semester.pk)

    def test_semester_field__leaves_out_semesters_that_are_not_open(self):
        """Students join a semester that is running: one still being set up or already archived
        is not something to register into."""
        baker.make(Semester, status=Semester.Status.UPCOMING)
        baker.make(Semester, status=Semester.Status.ARCHIVED)

        form = CourseStudentForm()

        self.assertEqual(list(form.fields['semester'].queryset), [SiteConfig.get().active_semester])

    def test_semester_field__stays_visible_under_simple_registration_when_several_are_open(self):
        """Simplified registration hides a field only when there is nothing to choose. With two
        semesters open there is a real choice, so the student is asked rather than silently
        landing in whichever one the form happened to default to."""
        config = SiteConfig.get()
        config.simplified_course_registration = True
        config.save()
        baker.make(Semester, status=Semester.Status.OPEN)

        form = CourseStudentForm(student_registration=True)

        self.assertNotIsInstance(form.fields['semester'].widget, forms.HiddenInput)

    def test_semester_field__hidden_under_simple_registration_when_only_one_is_open(self):
        """The usual deck runs one semester, and then there is nothing to ask: the field stays
        hidden and defaults to it."""
        config = SiteConfig.get()
        config.simplified_course_registration = True
        config.save()

        form = CourseStudentForm(student_registration=True)

        self.assertIsInstance(form.fields['semester'].widget, forms.HiddenInput)


class SemesterFormTest(ByteDeckTenantTestCase):
    """Validation tests for SemesterForm (the staff create/update semester form)."""

    def test_clean__last_day_before_first_day(self):
        """A semester whose last day falls before its first day is rejected with an error
        on the last_day field (the date-math methods assume a forward range)."""
        form = SemesterForm(data={'name': '', 'first_day': '2024-02-01', 'last_day': '2024-01-01'})
        self.assertFalse(form.is_valid())
        self.assertIn('last_day', form.errors)

    def test_clean__forward_or_single_day_range_is_valid(self):
        """A forward date range is accepted, including a single-day semester where the
        first and last day are equal."""
        form = SemesterForm(data={'name': '', 'first_day': '2024-01-01', 'last_day': '2024-02-01'})
        self.assertTrue(form.is_valid())

        form = SemesterForm(data={'name': '', 'first_day': '2024-01-01', 'last_day': '2024-01-01'})
        self.assertTrue(form.is_valid())


class XPCourseChoiceMixinTest(ByteDeckTenantTestCase):
    """The shared "which course does this XP count toward?" question (issue #2440).

    The forms that carry the mixin are tested where they live; what belongs here is that both
    of them ask it the same way, since the whole point of the mixin is one wording and one
    control wherever the question comes up.
    """

    @classmethod
    def setUpTestData(cls):
        """Register a student in two courses, so the question has something to ask about."""
        cls.student = baker.make(User)
        cls.maths = baker.make(Course, title='Maths')
        cls.art = baker.make(Course, title='Art')
        for course in (cls.maths, cls.art):
            baker.make(
                CourseStudent, user=cls.student, course=course, block=baker.make(Block),
                semester=SiteConfig.get().active_semester,
            )

    def test_course_field__is_asked_the_same_way_on_every_form_that_carries_it(self):
        """A student handing in a quest and a teacher granting a badge see the same question."""
        for form in (SubmissionQuickReplyFormStudent(student=self.student), BadgeAssertionForm(student=self.student)):
            with self.subTest(form=type(form).__name__):
                self.assertEqual(form.fields['course'].label, 'Which course should this XP be awarded to?')
                # the label asks the whole question, so nothing repeats it underneath
                self.assertEqual(form.fields['course'].help_text, '')
                self.assertIsInstance(form.fields['course'].widget, Select2Widget)

    def test_course_field__hands_its_choices_to_the_dropdown(self):
        """The widget is swapped in after the field is built, so the courses and the "split
        evenly" choice have to reach it: a select2 with no choices would render empty."""
        form = SubmissionQuickReplyFormStudent(student=self.student)

        self.assertCountEqual(
            [str(label) for value, label in form.fields['course'].widget.choices],
            ['Split evenly between my courses', str(self.maths), str(self.art)],
        )
