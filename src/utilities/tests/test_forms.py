from django.contrib.auth import get_user_model
from django.urls import reverse

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from utilities.forms import MenuItemForm


User = get_user_model()


class MenuItemFormTest(ByteDeckTenantTestCase):

    def test_MenuItemForm__allow_relative_urls(self):
        """ Form accepts a relative (path-only) url. """
        form_data = {
            'label': 'New Menu Item',
            'fa_icon': 'link',
            'url': reverse('courses:ranks'),
            'open_link_in_new_tab': False,
            'sort_order': 0,
            'visible': True,
        }
        form = MenuItemForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)

    def test_MenuItemForm__allow_absolute_urls(self):
        """ Form accepts an absolute url. """
        form_data = {
            'label': 'New Menu Item',
            'fa_icon': 'link',
            'url': 'https://github.com/bytedeck/bytedeck',
            'open_link_in_new_tab': False,
            'sort_order': 0,
            'visible': True,
        }
        form = MenuItemForm(data=form_data)
        self.assertTrue(form.is_valid(), form.errors)
