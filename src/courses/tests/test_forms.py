from courses.forms import SemesterForm
from hackerspace_online.tests.utils import ByteDeckTenantTestCase


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
