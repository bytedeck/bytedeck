"""Tests for the badge type and badge rarity Font Awesome icons: the bare-name storage,
the ``fa_icon_class`` render helper, the data migration that normalized both fields,
field validation, the icon-picker forms, and the badge-granted notification icon."""
from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import SimpleTestCase

from model_bakery import baker

from badges.admin import BadgeResource
from badges.forms import BadgeRarityForm, BadgeTypeForm
from badges.models import Badge, BadgeAssertion, BadgeRarity, BadgeType
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from notifications.models import Notification
from utilities.fa_icon_widget import FontAwesomeIconPickerWidget

# The normalizing splitter lives inside the data migration (kept self-contained
# there), so import it from that module to test it directly.
badge_migration = import_module("badges.migrations.0018_normalize_badge_fa_icon_names")

User = get_user_model()


class BadgeBareFaIconNameMigrationTest(SimpleTestCase):
    """The frozen splitter behind the badge data migration. Pure function, no database."""

    def test_bare_fa_icon_name__handles_every_stored_shape(self):
        """Prefixed values, whole class lists and sizing classes all reduce as documented,
        real icon names that merely start like a modifier class ("fa-spinner",
        "fa-life-ring") survive, and anything whose name the field would refuse (an
        underscore, an accent, a doubled prefix) gives "" rather than a junk value."""
        cases = [
            ("fa-gift", "gift"),
            ("fa-certificate", "certificate"),
            ("fa-hand-spock-o", "hand-spock-o"),
            ("fa fa-gift", "gift"),
            ("gift", "gift"),
            ("fa fa-fw fa-gift", "gift"),
            ("fa-gift fa-lg", "gift"),
            ("fa-spinner", "spinner"),
            ("fa-life-ring", "life-ring"),
            ("fa-stack-overflow", "stack-overflow"),
            ("fa-lg", ""),
            ("", ""),
            (None, ""),
            ("not an icon", ""),
            ("fa-user_name", ""),
            ("fa-\u00e9clair", ""),
            ("fa-fa-gift", ""),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(badge_migration.bare_fa_icon_name(raw), expected)


class BadgeFaIconDataMigrationTest(ByteDeckTenantTestCase):
    """The data migration reduces both fields to the bare name, and puts the prefix back
    if it is unapplied."""

    def test_normalize_fa_icon_names__reduces_prefixed_badge_type_and_rarity_icons(self):
        """A deck's existing "fa-gift" badge type and "fa-certificate" rarity become
        "gift" and "certificate", which is what the templates now render."""
        badge_type = baker.make(BadgeType, fa_icon="fa-gift")
        rarity = baker.make(BadgeRarity, fa_icon="fa-certificate", percentile=42.0)

        badge_migration.normalize_fa_icon_names(django_apps, None)

        badge_type.refresh_from_db()
        rarity.refresh_from_db()
        self.assertEqual(badge_type.fa_icon, "gift")
        self.assertEqual(rarity.fa_icon, "certificate")

    def test_normalize_fa_icon_names__leaves_bare_names_and_empty_icons_alone(self):
        """A badge type already storing a bare name keeps it, and one with no icon at
        all is left without one rather than being given a stray value."""
        named = baker.make(BadgeType, fa_icon="gift")
        blank = baker.make(BadgeType, fa_icon="")

        badge_migration.normalize_fa_icon_names(django_apps, None)

        named.refresh_from_db()
        blank.refresh_from_db()
        self.assertEqual(named.fa_icon, "gift")
        self.assertEqual(blank.fa_icon, "")

    def test_normalize_fa_icon_names__falls_back_to_certificate_for_an_unreadable_rarity(self):
        """A rarity always shows an icon, so a value nothing can be read out of gets the
        generic badge icon rather than being left blank."""
        rarity = baker.make(BadgeRarity, fa_icon="not an icon", percentile=43.0)

        badge_migration.normalize_fa_icon_names(django_apps, None)

        rarity.refresh_from_db()
        self.assertEqual(rarity.fa_icon, "certificate")

    def test_restore_fa_icon_prefixes__puts_the_prefix_back(self):
        """Unapplying the migration puts the "fa-" prefix back on both fields, so a stored
        value round-trips."""
        badge_type = baker.make(BadgeType, fa_icon="gift")
        rarity = baker.make(BadgeRarity, fa_icon="certificate", percentile=44.0)
        blank = baker.make(BadgeType, fa_icon="")

        badge_migration.restore_fa_icon_prefixes(django_apps, None)

        badge_type.refresh_from_db()
        rarity.refresh_from_db()
        blank.refresh_from_db()
        self.assertEqual(badge_type.fa_icon, "fa-gift")
        self.assertEqual(rarity.fa_icon, "fa-certificate")
        self.assertEqual(blank.fa_icon, "")


class BadgeTypeFaIconClassTest(ByteDeckTenantTestCase):
    """``BadgeType.fa_icon_class`` composes the ``<i class="...">`` list templates use."""

    def test_fa_icon_class__composes_the_class_list(self):
        """The stored bare name becomes ``fa fa-<name>``."""
        self.assertEqual(baker.make(BadgeType, fa_icon="gift").fa_icon_class, "fa fa-gift")

    def test_fa_icon_class__blank_when_the_type_has_no_icon(self):
        """A type with no icon composes nothing, so a template renders no stray "fa fa-"."""
        self.assertEqual(baker.make(BadgeType, fa_icon="").fa_icon_class, "")
        self.assertEqual(baker.make(BadgeType, fa_icon=None).fa_icon_class, "")


class BadgeRarityFaIconTest(ByteDeckTenantTestCase):
    """``BadgeRarity`` composes its icon class list and its coloured icon HTML."""

    def test_fa_icon_class__composes_the_class_list(self):
        """The stored bare name becomes ``fa fa-<name>``."""
        rarity = baker.make(BadgeRarity, fa_icon="certificate", percentile=45.0)
        self.assertEqual(rarity.fa_icon_class, "fa fa-certificate")

    def test_get_icon_html__carries_the_class_list_once(self):
        """The rarity icon (rendered |safe on the badge page) names the icon once, with
        no doubled "fa" from the markup also carrying one."""
        rarity = baker.make(BadgeRarity, name="Fabled", color="orangered",
                            fa_icon="certificate", percentile=46.0)

        html = rarity.get_icon_html()

        self.assertIn("fa fa-certificate", html)
        self.assertNotIn("fa fa fa-", html)
        self.assertIn("rarity-Fabled", html)
        self.assertIn("color:orangered", html)


class BadgeGrantedNotificationIconTest(ByteDeckTenantTestCase):
    """The badge-granted notification builds its icon from the badge type's class list."""

    def setUp(self):
        """A student to grant to and a teacher to grant it."""
        self.student = baker.make(User)
        self.teacher = baker.make(User, is_staff=True)

    def test_post_save_receiver__falls_back_to_the_generic_badge_icon(self):
        """A badge type with no icon of its own grants a notification showing the generic
        certificate, named once (the default branch of post_save_receiver)."""
        badge = baker.make(Badge, badge_type=baker.make(BadgeType, fa_icon=""))

        BadgeAssertion.objects.create_assertion(self.student, badge, issued_by=self.teacher)

        notification = Notification.objects.all_for_user(self.student).last()
        self.assertIn("fa fa-certificate", notification.font_icon)
        self.assertNotIn("fa fa fa-", notification.font_icon)

    def test_post_save_receiver__cannot_carry_markup_from_an_imported_icon(self):
        """A badge CSV is imported without a form, so a crafted icon column would otherwise
        reach this notification, which is rendered |safe in the notification list. The name
        is dropped on import, so the notification shows the generic certificate instead."""
        row = {"badge_type_name": "Crafted", "badge_type_sort": 1,
               "badge_type_icon": 'x"onmouseover=alert(1)'}
        BadgeResource().generate_badge_type(row)
        badge_type = BadgeType.objects.get(name="Crafted")
        self.assertEqual(badge_type.fa_icon, "")

        badge = baker.make(Badge, badge_type=badge_type)
        BadgeAssertion.objects.create_assertion(self.student, badge, issued_by=self.teacher)

        notification = Notification.objects.all_for_user(self.student).last()
        self.assertNotIn("onmouseover", notification.font_icon)
        self.assertIn("fa fa-certificate", notification.font_icon)


class BadgeTypeFormIconPickerTest(ByteDeckTenantTestCase):
    """The badge type form offers the icon picker and holds the field to a bare name."""

    def test_BadgeTypeForm__uses_the_icon_picker_widget(self):
        """The icon field is the searchable picker rather than a plain text box."""
        self.assertIsInstance(BadgeTypeForm().fields["fa_icon"].widget, FontAwesomeIconPickerWidget)

    def test_BadgeTypeForm__labels_the_icon_field_in_plain_language(self):
        """The field reads "Icon", not the "Fa icon" Django would derive from its name."""
        self.assertEqual(BadgeTypeForm().fields["fa_icon"].label, "Icon")

    def test_BadgeTypeForm__rejects_a_prefixed_icon_name(self):
        """The field holds a bare name, so typing "fa-gift" fails validation."""
        form = BadgeTypeForm(data={"name": "Picker Badge Type", "sort_order": 1, "fa_icon": "fa-gift"})
        self.assertFalse(form.is_valid())
        self.assertIn("fa_icon", form.errors)

    def test_BadgeTypeForm__rejects_markup(self):
        """A value carrying markup cannot reach the notification icon HTML."""
        form = BadgeTypeForm(data={"name": "Picker Badge Type", "sort_order": 1,
                                   "fa_icon": "'></i><script>alert(1)</script>"})
        self.assertFalse(form.is_valid())
        self.assertIn("fa_icon", form.errors)

    def test_BadgeTypeForm__accepts_a_bare_icon_name(self):
        """A bare name, which is what the picker writes, validates."""
        form = BadgeTypeForm(data={"name": "Picker Badge Type", "sort_order": 1, "fa_icon": "gift"})
        self.assertTrue(form.is_valid(), form.errors)


class BadgeRarityFormIconPickerTest(ByteDeckTenantTestCase):
    """The admin-only rarity form offers the same picker, plus the stylesheets the admin
    does not load on its own."""

    def test_BadgeRarityForm__uses_the_icon_picker_widget(self):
        """The icon field is the searchable picker rather than a plain text box."""
        self.assertIsInstance(BadgeRarityForm().fields["fa_icon"].widget, FontAwesomeIconPickerWidget)

    def test_BadgeRarityForm__labels_the_icon_field_in_plain_language(self):
        """The field reads "Icon", not the "Fa icon" Django would derive from its name."""
        self.assertEqual(BadgeRarityForm().fields["fa_icon"].label, "Icon")

    def test_BadgeRarityForm_media__loads_font_awesome_and_both_picker_stylesheets(self):
        """The form's media carries the picker's own assets and the admin extras, so the
        icon grid is visible and laid out inside the admin."""
        media = str(BadgeRarityForm().media)
        self.assertIn("css/fa_icon_picker.css", media)
        self.assertIn("css/font-awesome-4.7.0.min.css", media)
        self.assertIn("css/fa_icon_picker_admin.css", media)
        self.assertIn("js/fa_icon_picker.js", media)

    def test_BadgeRarityForm__rejects_a_prefixed_icon_name(self):
        """The rarity field holds a bare name, so typing "fa-certificate" fails validation."""
        form = BadgeRarityForm(data={"name": "Picker Rarity", "percentile": 47.0, "color": "gold",
                                     "fa_icon": "fa-certificate"})
        self.assertFalse(form.is_valid())
        self.assertIn("fa_icon", form.errors)

    def test_BadgeRarityForm__accepts_a_bare_icon_name(self):
        """A bare name, which is what the picker writes, validates."""
        form = BadgeRarityForm(data={"name": "Picker Rarity", "percentile": 47.0, "color": "gold",
                                     "fa_icon": "certificate"})
        self.assertTrue(form.is_valid(), form.errors)


class BadgeTypeCreateViewIconPickerTest(ByteDeckTenantTestCase):
    """The badge type add page serves the picker and its assets, and a bare name posts through."""

    def setUp(self):
        """A staff user, since badge types are staff-only."""
        self.client.force_login(baker.make(User, is_staff=True, is_active=True))

    def test_badge_type_create__renders_picker_and_media(self):
        """The page includes the picker markup and loads its stylesheet, the shared icon
        list and the picker JS."""
        response = self.client.get(reverse("badges:badge_type_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fa-icon-picker")
        self.assertContains(response, "css/fa_icon_picker.css")
        self.assertContains(response, "js/fa_icons_4.7.0.js")
        self.assertContains(response, "js/fa_icon_picker.js")

    def test_badge_type_create__stores_the_bare_name(self):
        """Posting a bare name stores it as-is and it composes back into a class list."""
        response = self.client.post(reverse("badges:badge_type_create"),
                                    data={"name": "Picker Type", "sort_order": 9, "fa_icon": "rocket"})
        self.assertRedirects(response, reverse("badges:badge_types"))
        badge_type = BadgeType.objects.get(name="Picker Type")
        self.assertEqual(badge_type.fa_icon, "rocket")
        self.assertEqual(badge_type.fa_icon_class, "fa fa-rocket")


class BadgeTypeIconRoundTripTest(ByteDeckTenantTestCase):
    """A badge CSV keeps working across the change of format."""

    def test_badge_type_icon__round_trips_through_export_and_import(self):
        """A bare icon name exported from a deck imports back unchanged, and a CSV naming
        it with the "fa-" prefix arrives with the prefix dropped."""
        resource = BadgeResource()
        badge_type = baker.make(BadgeType, name="Gold", fa_icon="star")
        badge = baker.make(Badge, badge_type=badge_type)
        exported = resource.dehydrate_badge_type_icon(badge)

        row = {"badge_type_name": "Imported", "badge_type_sort": 1, "badge_type_icon": exported}
        resource.generate_badge_type(row)
        self.assertEqual(BadgeType.objects.get(name="Imported").fa_icon, "star")

        legacy_row = {"badge_type_name": "Legacy", "badge_type_sort": 1, "badge_type_icon": "fa-star"}
        resource.generate_badge_type(legacy_row)
        self.assertEqual(BadgeType.objects.get(name="Legacy").fa_icon, "star")
