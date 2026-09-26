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

    def menu_item_form(self, url):
        """A MenuItemForm filled in with ``url`` and otherwise valid data."""
        return MenuItemForm(data={
            'label': 'New Menu Item',
            'fa_icon': 'link',
            'url': url,
            'open_link_in_new_tab': False,
            'sort_order': 0,
            'visible': True,
        })

    def test_MenuItemForm__refuses_a_relative_url_that_leads_to_no_page(self):
        """A mistyped path ("rank" for "ranks") is refused with a message naming it, rather than saved as a link to a 404."""
        form = self.menu_item_form('/courses/rank/')

        self.assertFalse(form.is_valid())
        self.assertEqual(
            form.errors['url'],
            ['No page on this deck has the address "/courses/rank/". Check it for a typo, '
             'or copy it from the address bar of the page you want to link to.'],
        )

    def test_MenuItemForm__accepts_a_path_without_its_trailing_slash(self):
        """The ranks page's path without its closing "/" passes: Django redirects it to the path with one."""
        form = self.menu_item_form(reverse('courses:ranks').rstrip('/'))
        self.assertTrue(form.is_valid(), form.errors)

    def test_MenuItemForm__checks_only_the_path_of_a_relative_url(self):
        """A query string and a fragment after a page's path don't stop it matching the page."""
        form = self.menu_item_form(reverse('courses:ranks') + '?sort=xp#top')
        self.assertTrue(form.is_valid(), form.errors)

    def test_MenuItemForm__accepts_links_to_uploaded_and_static_files(self):
        """Paths under MEDIA_URL and STATIC_URL pass: the web server serves them, so no url pattern matches them."""
        for url in ['/media/course-outline.pdf', '/static/img/logo.png']:
            with self.subTest(url=url):
                form = self.menu_item_form(url)
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
