"""Tests for the pieces every Font Awesome icon field shares: the ``bare_icon_name`` /
``fa_icon_class`` helpers, the validator and help text, the picker widget's media (and
the admin variant of it), and the menu item that uses them."""
from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.shortcuts import reverse
from django.test import SimpleTestCase

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from utilities.fa_icon import FA_ICON_HELP_TEXT, FA_ICON_VALIDATOR, bare_icon_name, fa_icon_class
from utilities.fa_icon_widget import FontAwesomeAdminFormMixin, FontAwesomeIconPickerWidget
from utilities.forms import MenuItemForm
from utilities.models import MenuItem

# The normalizing splitter lives inside the data migration (kept self-contained
# there), so import it from that module to test it directly.
menuitem_migration = import_module("utilities.migrations.0003_normalize_menuitem_fa_icon_name")

User = get_user_model()


class BareIconNameTest(SimpleTestCase):
    """``bare_icon_name`` reduces any stored value to the bare Font Awesome name.
    Pure function, so no database is needed."""

    def test_bare_icon_name__handles_every_stored_shape(self):
        """Bare names pass through, the "fa-" and "fa fa-" shapes are reduced, surrounding
        whitespace is trimmed, and empty values stay empty."""
        cases = [
            ("star", "star"),
            ("star-o", "star-o"),
            ("  star  ", "star"),
            ("fa-star", "star"),
            ("fa fa-star", "star"),
            ("", ""),
            (None, ""),
            ("   ", ""),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(bare_icon_name(raw), expected)

    def test_bare_icon_name__drops_a_value_the_field_would_refuse(self):
        """A value that never went through a form (a CSV import, a row edited straight in
        the database) is held to the same names the validator accepts, so markup, quotes
        and a doubled prefix all give "" rather than reaching the class attribute."""
        for bad in ['x"onmouseover=alert(1)', "'></i><script>alert(1)</script>", "Star", "star;", "fa-fa-star"]:
            with self.subTest(bad=bad):
                self.assertEqual(bare_icon_name(bad), "")


class FaIconClassTest(SimpleTestCase):
    """``fa_icon_class`` composes the ``<i class="...">`` list templates use."""

    def test_fa_icon_class__name_only(self):
        """A bare name becomes ``fa fa-<name>``."""
        self.assertEqual(fa_icon_class("gift"), "fa fa-gift")

    def test_fa_icon_class__name_with_modifiers(self):
        """Modifier classes are appended after the icon."""
        self.assertEqual(fa_icon_class("forward", "fa-rotate-270"), "fa fa-forward fa-rotate-270")

    def test_fa_icon_class__blank_when_no_icon(self):
        """No icon means no class list at all, so a template renders a bare <i>."""
        self.assertEqual(fa_icon_class(""), "")
        self.assertEqual(fa_icon_class(None), "")
        self.assertEqual(fa_icon_class("", "fa-lg"), "")

    def test_fa_icon_class__ignores_surrounding_whitespace(self):
        """Whitespace around the name and the modifiers is trimmed."""
        self.assertEqual(fa_icon_class("  gift  ", "   "), "fa fa-gift")

    def test_fa_icon_class__renders_a_value_that_carries_its_prefix(self):
        """A stored value carrying the "fa-" prefix (a CSV import, say) renders the icon
        with a single prefix rather than "fa fa-fa-gift"."""
        self.assertEqual(fa_icon_class("fa-gift"), "fa fa-gift")

    def test_fa_icon_class__drops_modifier_tokens_that_are_not_class_names(self):
        """Templates render the composed list inside class="...", so a modifier value
        carrying a quote is dropped and the real modifier beside it is kept."""
        self.assertEqual(fa_icon_class("gift", 'fa-lg x"onmouseover=alert(1)'), "fa fa-gift fa-lg")


class FaIconValidatorTest(SimpleTestCase):
    """The validator every icon field shares holds a value to one safe, bare name."""

    def test_fa_icon_validator__rejects_class_lists_prefixes_and_markup(self):
        """A "fa-" prefix, a whole class list, uppercase, or markup are all refused."""
        for bad in ["fa-star", "fa fa-star", "Star", "star o", "'></i><script>alert(1)</script>", "star;"]:
            with self.subTest(bad=bad):
                with self.assertRaises(ValidationError):
                    FA_ICON_VALIDATOR(bad)

    def test_fa_icon_validator__accepts_bare_names_and_empty(self):
        """A lowercase bare name (hyphens allowed) and an empty value both pass."""
        for good in ["star", "star-o", "hand-spock-o", ""]:
            with self.subTest(good=good):
                FA_ICON_VALIDATOR(good)

    def test_fa_icon_help_text__links_the_pinned_font_awesome_version(self):
        """The help text points at the 4.7.0 icon list, the version the app vendors, so a
        user cannot be sent to a modern list full of names 4.7.0 does not have."""
        self.assertIn("https://fontawesome.com/v4.7.0/icons/", FA_ICON_HELP_TEXT)


class FontAwesomeIconPickerWidgetMediaTest(SimpleTestCase):
    """The picker's assets travel with the widget, so it works wherever it is rendered."""

    def test_widget_media__includes_stylesheet_icon_list_and_picker(self):
        """The widget's media carries its own stylesheet plus the shared icon list and the
        picker JS that reads it."""
        media = str(FontAwesomeIconPickerWidget().media)
        self.assertIn("css/fa_icon_picker.css", media)
        self.assertIn("js/fa_icons_4.7.0.js", media)
        self.assertIn("js/fa_icon_picker.js", media)

    def test_admin_form_mixin_media__adds_font_awesome_and_admin_layout(self):
        """An admin form built on the mixin also loads Font Awesome itself and the
        admin-only layout sheet, neither of which the admin provides."""
        media = str(FontAwesomeAdminFormMixin.Media.css)
        self.assertIn("css/font-awesome-4.7.0.min.css", media)
        self.assertIn("css/fa_icon_picker_admin.css", media)


class MenuItemBareFaIconNameMigrationTest(SimpleTestCase):
    """The frozen splitter behind the menu item data migration. Pure function, no database."""

    def test_bare_fa_icon_name__handles_every_stored_shape(self):
        """Prefixed values, whole class lists, sizing classes and unparseable values all
        reduce as documented, real icon names that merely start like a modifier class
        ("fa-spinner", "fa-life-ring") survive, and anything whose name the field would
        refuse (an underscore, an accent, a doubled prefix) gives "" rather than a junk
        value."""
        cases = [
            ("fa-star", "star"),
            ("fa fa-star", "star"),
            ("star-o", "star-o"),
            ("  fa fa-th-large  ", "th-large"),
            ("fa fa-fw fa-star", "star"),
            ("fa-star fa-lg", "star"),
            ("fa-spinner", "spinner"),
            ("fa-life-ring", "life-ring"),
            ("fa-stack-overflow", "stack-overflow"),
            ('<i class="fa fa-star"></i>', "star"),
            ("fa-rotate-90", ""),
            ("", ""),
            (None, ""),
            ("foo bar", ""),
            ("fa-user_name", ""),
            ("fa-\u00e9clair", ""),
            ("fa-fa-star", ""),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(menuitem_migration.bare_fa_icon_name(raw), expected)


class MenuItemFaIconTest(ByteDeckTenantTestCase):
    """A menu item renders its icon through the shared helper, and the data migration
    reduces a value carrying the "fa-" prefix a user typed."""

    def test_fa_icon_class__composes_the_class_list(self):
        """The stored bare name becomes ``fa fa-<name>``."""
        self.assertEqual(baker.make(MenuItem, fa_icon="star-o", url="/courses/ranks/").fa_icon_class, "fa fa-star-o")

    def test_str__renders_the_link_with_one_fa_prefix(self):
        """The menu link's HTML (rendered |safe in the navbar) carries the icon's class
        list once, with no doubled "fa-" from the template also prefixing it."""
        menu_item = baker.make(MenuItem, fa_icon="star-o", label="Ranks", url="/courses/ranks/", open_link_in_new_tab=False)
        self.assertIn('<i class="fa-fw fa fa-star-o"></i>', str(menu_item))
        self.assertNotIn("fa-fa-", str(menu_item))

    def test_normalize_fa_icon_names__reduces_a_value_that_kept_its_prefix(self):
        """The data migration turns a menu item icon typed as "fa-star-o" into "star-o",
        which is what actually renders."""
        menu_item = baker.make(MenuItem, fa_icon="fa-star-o", url="/courses/ranks/")

        menuitem_migration.normalize_fa_icon_names(django_apps, None)

        menu_item.refresh_from_db()
        self.assertEqual(menu_item.fa_icon, "star-o")

    def test_normalize_fa_icon_names__leaves_a_bare_name_alone(self):
        """An icon already stored as a bare name is not rewritten."""
        menu_item = baker.make(MenuItem, fa_icon="star-o", url="/courses/ranks/")

        menuitem_migration.normalize_fa_icon_names(django_apps, None)

        menu_item.refresh_from_db()
        self.assertEqual(menu_item.fa_icon, "star-o")


class MenuItemFormIconPickerTest(ByteDeckTenantTestCase):
    """The menu item form offers the icon picker and holds the field to a bare name."""

    def test_MenuItemForm__uses_the_icon_picker_widget(self):
        """The icon field is the searchable picker rather than a plain text box."""
        form = MenuItemForm()
        self.assertIsInstance(form.fields["fa_icon"].widget, FontAwesomeIconPickerWidget)

    def test_MenuItemForm__labels_the_icon_field_in_plain_language(self):
        """The field reads "Icon", not the "Fa icon" Django would derive from its name."""
        self.assertEqual(MenuItemForm().fields["fa_icon"].label, "Icon")

    def test_MenuItemForm__rejects_a_prefixed_icon_name(self):
        """Typing "fa-star" fails validation: the field stores the bare name."""
        form = MenuItemForm(data={
            "label": "Ranks", "fa_icon": "fa-star", "url": "/courses/ranks/",
            "open_link_in_new_tab": False, "sort_order": 0,
        })
        self.assertFalse(form.is_valid())
        self.assertIn("fa_icon", form.errors)

    def test_MenuItemForm__accepts_a_bare_icon_name(self):
        """A bare name, which is what the picker writes, validates."""
        form = MenuItemForm(data={
            "label": "Ranks", "fa_icon": "star-o", "url": "/courses/ranks/",
            "open_link_in_new_tab": False, "sort_order": 0,
        })
        self.assertTrue(form.is_valid(), form.errors)


class MenuItemCreateViewIconPickerTest(ByteDeckTenantTestCase):
    """The menu item add page serves the picker and its assets."""

    def setUp(self):
        """A staff user, since menu items are staff-only."""
        self.client.force_login(baker.make(User, is_staff=True, is_active=True))

    def test_menu_item_create__renders_picker_and_media(self):
        """The page includes the picker markup and loads its stylesheet, the shared icon
        list and the picker JS."""
        response = self.client.get(reverse("utilities:menu_item_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fa-icon-picker")
        self.assertContains(response, "css/fa_icon_picker.css")
        self.assertContains(response, "js/fa_icons_4.7.0.js")
        self.assertContains(response, "js/fa_icon_picker.js")
