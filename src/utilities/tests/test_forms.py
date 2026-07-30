from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from prerequisites.forms import PrereqFormInline
from utilities.fields import GFKChoiceField
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


class FutureModelFormTest(ByteDeckTenantTestCase):
    """utilities.forms.FutureModelForm populates initial data from each field's value_from_object()."""

    def test_init__field_whose_value_from_object_raises_is_skipped(self):
        """A field whose value_from_object() raises is skipped during initial population instead of crashing the form."""
        # PrereqFormInline is a FutureModelForm with GFKChoiceField fields; make their
        # value_from_object blow up so __init__ takes the guarded except/continue path.
        with patch.object(GFKChoiceField, "value_from_object", side_effect=ValueError("boom")):
            form = PrereqFormInline()
        self.assertNotIn("prereq_object", form.initial)
