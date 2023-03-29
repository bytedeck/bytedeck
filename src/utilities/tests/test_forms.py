from django.contrib.auth import get_user_model
from django.urls import reverse

from django_tenants.test.cases import TenantTestCase

from utilities.forms import MenuItemForm


User = get_user_model()


class MenuItemFormTest(TenantTestCase):

    def test_MenuItem_form_allow_relative_urls(self):
        form_data = {
            'label': 'New Menu Item',
            'fa_icon': 'link',
            'url': reverse('courses:ranks'),
            'open_link_in_new_tab': False,
            'sort_order': 0,
            'visible': True,
        }
        form = MenuItemForm(data=form_data)
        self.assertTrue(form.is_valid)

    def test_MenuItem_form_allow_absolute_urls(self):
        form_data = {
            'label': 'New Menu Item',
            'fa_icon': 'link',
            'url': 'https://github.com/bytedeck/bytedeck',
            'open_link_in_new_tab': False,
            'sort_order': 0,
            'visible': True,
        }
        form = MenuItemForm(data=form_data)
        self.assertTrue(form.is_valid)
