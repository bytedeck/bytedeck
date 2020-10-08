from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker

from badges.forms import BadgeAssertionForm, BulkBadgeAssertionForm

User = get_user_model()


class BadgeAssertionFormTest(TenantTestCase):

    def test_badge_assertion_form(self):
        form_data = {
            'badge': baker.make('badges.Badge'),
            'user': baker.make(User)
        }
        form = BadgeAssertionForm(data=form_data)
        self.assertTrue(form.is_valid)

    def test_bulk_badge_assertion_form(self):
        form_data = {
            'badge': baker.make('badges.Badge'),
            'students': [baker.make(User).profile, baker.make(User).profile]
        }
        form = BulkBadgeAssertionForm(data=form_data)
        self.assertTrue(form.is_valid)
