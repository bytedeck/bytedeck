from django import forms
from model_bakery import baker

from courses.forms import CourseStudentForm, SemesterForm
from courses.models import Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig


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
