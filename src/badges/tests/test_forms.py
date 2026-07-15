from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker

from badges.forms import BadgeAssertionForm, BulkBadgeAssertionForm

User = get_user_model()


class BadgeAssertionFormTest(TenantTestCase):

    def test_badge_assertion_form(self):
        """ Form with a badge and user is valid. """
        form_data = {
            'badge': baker.make('badges.Badge').pk,
            'user': baker.make(User).pk
        }
        form = BadgeAssertionForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_badge_assertion_form_no_xp(self):
        """ Form is still valid when the do_not_grant_xp option is checked. """
        form_data = {
            'badge': baker.make('badges.Badge').pk,
            'user': baker.make(User).pk,
            'do_not_grant_xp': True,
        }
        form = BadgeAssertionForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_bulk_badge_assertion_form(self):
        """ Form with a badge and a list of student profiles is valid. """
        form_data = {
            'badge': baker.make('badges.Badge').pk,
            'students': [baker.make(User).profile.pk, baker.make(User).profile.pk]
        }
        form = BulkBadgeAssertionForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
