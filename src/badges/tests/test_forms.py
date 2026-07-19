from django.contrib.auth import get_user_model

from model_bakery import baker

from badges.forms import BadgeAssertionForm, BulkBadgeAssertionForm
from hackerspace_online.tests.utils import ByteDeckTenantTestCase

User = get_user_model()


class BadgeAssertionFormTest(ByteDeckTenantTestCase):

    def test_badge_assertion_form__valid_with_badge_and_user(self):
        """ Form with a badge and user is valid. """
        form_data = {
            'badge': baker.make('badges.Badge').pk,
            'user': baker.make(User).pk
        }
        form = BadgeAssertionForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_badge_assertion_form__valid_with_do_not_grant_xp(self):
        """ Form is still valid when the do_not_grant_xp option is checked. """
        form_data = {
            'badge': baker.make('badges.Badge').pk,
            'user': baker.make(User).pk,
            'do_not_grant_xp': True,
        }
        form = BadgeAssertionForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_bulk_badge_assertion_form__valid_with_badge_and_students(self):
        """ Form with a badge and a list of student profiles is valid. """
        form_data = {
            'badge': baker.make('badges.Badge').pk,
            'students': [baker.make(User).profile.pk, baker.make(User).profile.pk]
        }
        form = BulkBadgeAssertionForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
