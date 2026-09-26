import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase
from django.urls import reverse

from django_summernote.utils import get_config

from bytedeck_summernote.widgets import (
    ByteDeckSummernoteAdvancedInplaceWidget,
    ByteDeckSummernoteAdvancedWidget,
    ByteDeckSummernoteSafeInplaceWidget,
    ByteDeckSummernoteSafeWidget,
)

from hackerspace_online.tests.utils import ByteDeckTenantTestCase


class TestByteDeckSummernoteSafeWidget(ByteDeckTenantTestCase):
    """ByteDeck's Summernote implementation, so called 'Safe' variant"""

    def test_widget__safe_cleans_xss(self):
        """Safe widget (iframe variant) input is "cleaned" to prevent XSS scripts from executing"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        widget = ByteDeckSummernoteSafeWidget()
        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})
        url = reverse("bytedeck_summernote-editor", kwargs={"id": "id_foobar"})

        assert url in html
        assert 'id="id_foobar"' in html

        illegal_tags = '<script>alert("Hello")</script>'
        value = widget.value_from_datadict({"foobar": illegal_tags}, {}, "foobar")

        self.assertEqual(value, '&lt;script&gt;alert("Hello")&lt;/script&gt;')

    def test_widget_inplace__safe_cleans_xss(self):
        """Safe widget (non-iframe aka inplace variant) input is "cleaned" to prevent XSS scripts from executing"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeInplaceWidget

        widget = ByteDeckSummernoteSafeInplaceWidget()

        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})

        assert "summernote" in html

        illegal_tags = '<script>alert("Hello")</script>'
        value = widget.value_from_datadict({"foobar": illegal_tags}, {}, "foobar")

        self.assertEqual(value, '&lt;script&gt;alert("Hello")&lt;/script&gt;')

    def test_config_codeview_filter__safe_enabled(self):
        """Safe widget (iframe variant) configured to prevent XSS scripts from executing"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        widget = ByteDeckSummernoteSafeWidget()
        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})

        assert '"codeviewFilter": true' in html


class TestByteDeckSummernoteAdvancedWidget(ByteDeckTenantTestCase):
    """ByteDeck's Summernote implementation, so called 'Advanced' variant"""

    def test_widget__advanced_preserves_input(self):
        """Advanced widget (iframe variant) input is preserved "as-is", no sanitization is done"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        widget = ByteDeckSummernoteAdvancedWidget()
        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})
        url = reverse("bytedeck_summernote-editor", kwargs={"id": "id_foobar"})

        assert url in html
        assert 'id="id_foobar"' in html

        illegal_tags = '<script>alert("Hello")</script>'
        value = widget.value_from_datadict({"foobar": illegal_tags}, {}, "foobar")

        self.assertEqual(value, '<script>alert("Hello")</script>')

    def test_widget_inplace__advanced_preserves_input(self):
        """Advanced widget (non-iframe aka inplace variant) input is preserved "as-is", no sanitization is done"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedInplaceWidget

        widget = ByteDeckSummernoteAdvancedInplaceWidget()

        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})

        assert "summernote" in html

        illegal_tags = '<script>alert("Hello")</script>'
        value = widget.value_from_datadict({"foobar": illegal_tags}, {}, "foobar")

        self.assertEqual(value, '<script>alert("Hello")</script>')

    def test_config_codeview_filter__advanced_disabled(self):
        """Advanced widget (iframe variant) configured to disable XSS protection"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        widget = ByteDeckSummernoteAdvancedWidget()
        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})

        assert '"codeviewFilter": false' in html


class TestByteDeckSummernoteMenus(SimpleTestCase):
    """The toolbar, and the menus that pop up over a clicked image, link or table."""

    # A button's name as Summernote and its plugins register it: context.memo('button.<name>', ...)
    BUTTON_NAME = re.compile(r"""memo\(\s*["']button\.([\w-]+)["']""")

    def registered_buttons(self, script_urls):
        """The buttons that Summernote itself, and those of the given scripts served from our own static files, register."""
        paths = ['summernote/summernote.min.js']
        paths += [url.removeprefix(settings.STATIC_URL) for url in script_urls if url.startswith(settings.STATIC_URL)]
        names = set()
        for path in paths:
            with open(finders.find(path), encoding='utf-8') as script:
                names.update(self.BUTTON_NAME.findall(script.read()))
        return names

    def test_summernote_settings__carry_the_pop_up_menus(self):
        """Every editor widget hands Summernote the configured menus, with the buttons our plugins add: Image Shapes
        over an image, and Table Headers and Table Styles over a table (#268)."""
        widget_classes = (
            ByteDeckSummernoteSafeWidget,
            ByteDeckSummernoteSafeInplaceWidget,
            ByteDeckSummernoteAdvancedWidget,
            ByteDeckSummernoteAdvancedInplaceWidget,
        )
        for widget_class in widget_classes:
            with self.subTest(widget=widget_class.__name__):
                popover = widget_class().summernote_settings()['popover']
                self.assertIn(['custom', ['imageShapes']], popover['image'])
                self.assertIn(['custom', ['tableHeaders', 'tableStyles']], popover['table'])

    def test_config__names_only_buttons_that_exist(self):
        """Every button that the toolbar and the menus name is registered by Summernote or by a plugin the editor
        loads, in both the iframe and the inplace editor. Summernote skips a name it doesn't know without a word, so a
        misspelled or renamed button would simply be missing from the editor (#268)."""
        summernote = get_config()['summernote']
        named = {
            button
            for groups in [summernote['toolbar'], *summernote['popover'].values()]
            for _group, buttons in groups
            for button in buttons
        }
        for scripts in ('js', 'js_for_inplace'):
            with self.subTest(scripts=scripts):
                self.assertEqual(named - self.registered_buttons(get_config()[scripts]), set())
