"""Tests for the Rank Font Awesome icon: the bare-name + modifiers storage, the
``fa_icon_class`` render helper, the legacy-value splitter behind the data
migration, the icon-picker widget/form, and the rank-up notification icon."""
from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django.test import SimpleTestCase

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from courses.fa_icon_utils import split_fa_icon_value
from courses.forms import RankForm
from courses.models import Rank
from siteconfig.models import SiteConfig
from utilities.fa_icon_widget import FontAwesomeIconPickerWidget

User = get_user_model()


class SplitFaIconValueTest(SimpleTestCase):
    """``split_fa_icon_value`` turns any legacy ``fa_icon`` class list into a
    ``(bare_name, modifiers)`` pair. Pure function, so no database is needed."""

    def test_split_fa_icon_value__handles_every_historical_shape(self):
        """Full class lists, prefix-only, already-bare, whitespace, buried-in-HTML,
        and unparseable values all split as documented."""
        cases = [
            ("fa fa-star", ("star", "")),
            ("fa fa-forward fa-rotate-270", ("forward", "fa-rotate-270")),
            ("fa fa-pause fa-rotate-90", ("pause", "fa-rotate-90")),
            ("fa-diamond", ("diamond", "")),
            ("star-o", ("star-o", "")),
            ("  fa fa-th-large  ", ("th-large", "")),
            ('<i class="fa fa-star"></i>', ("star", "")),
            ("", ("", "")),
            (None, ("", "")),
            ("foo bar", ("", "")),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(split_fa_icon_value(raw), expected)


class RankFaIconClassTest(ByteDeckTenantTestCase):
    """``Rank.fa_icon_class`` composes the ``<i class="...">`` list templates use."""

    def test_fa_icon_class__name_only(self):
        """A bare name becomes ``fa fa-<name>``."""
        rank = baker.make(Rank, fa_icon="star", fa_icon_modifiers="")
        self.assertEqual(rank.fa_icon_class, "fa fa-star")

    def test_fa_icon_class__name_with_modifiers(self):
        """Modifier classes are appended after the icon."""
        rank = baker.make(Rank, fa_icon="forward", fa_icon_modifiers="fa-rotate-270")
        self.assertEqual(rank.fa_icon_class, "fa fa-forward fa-rotate-270")

    def test_fa_icon_class__blank_when_no_icon(self):
        """No icon yields '' (so a template renders a bare ``<i>``, not "fa fa-")."""
        self.assertEqual(baker.make(Rank, fa_icon="", fa_icon_modifiers="").fa_icon_class, "")
        self.assertEqual(baker.make(Rank, fa_icon=None, fa_icon_modifiers="").fa_icon_class, "")

    def test_fa_icon_class__strips_surrounding_whitespace(self):
        """Stray whitespace in either field is trimmed out of the class list."""
        rank = baker.make(Rank, fa_icon="  star  ", fa_icon_modifiers="   ")
        self.assertEqual(rank.fa_icon_class, "fa fa-star")


class CreateZeroRankTest(ByteDeckTenantTestCase):
    """The zero rank carries a Font Awesome icon in ``fa_icon``, not a bogus value
    in the ``icon`` ImageField (the bug this fixes)."""

    def test_create_zero_rank__sets_fa_icon_and_leaves_image_empty(self):
        """create_zero_rank stores the icon as the bare name 'circle-o' and leaves
        the ImageField empty, so the rank falls back to the default icon URL."""
        Rank.objects.all().delete()
        zero = Rank.objects.create_zero_rank()
        self.assertEqual(zero.fa_icon, "circle-o")
        self.assertEqual(zero.fa_icon_class, "fa fa-circle-o")
        self.assertFalse(zero.icon)
        self.assertEqual(zero.get_icon_url(), SiteConfig.get().get_default_icon_url())


class RankFormTest(ByteDeckTenantTestCase):
    """RankForm wires the icon picker onto ``fa_icon`` and keeps the modifier field."""

    def test_rank_form__uses_icon_picker_widget(self):
        """The fa_icon field renders through the picker widget, and the modifier
        field is present for rotations/stacks."""
        form = RankForm()
        self.assertIsInstance(form.fields["fa_icon"].widget, FontAwesomeIconPickerWidget)
        self.assertIn("fa_icon_modifiers", form.fields)

    def test_rank_form__media_pulls_in_the_picker_assets(self):
        """The form advertises the shared icon list and the picker JS via its media."""
        media = str(RankForm().media)
        self.assertIn("js/fa_icons_4.7.0.js", media)
        self.assertIn("js/fa_icon_picker.js", media)


class FontAwesomeIconPickerWidgetTest(SimpleTestCase):
    """The reusable picker widget renders its chrome and merges its marker class.
    Pure rendering, so no database is needed."""

    def test_widget__merges_marker_class_with_caller_class(self):
        """A caller-supplied class is kept, and the picker's hook class is added."""
        widget = FontAwesomeIconPickerWidget(attrs={"class": "my-class"})
        self.assertIn("my-class", widget.attrs["class"])
        self.assertIn("fa-icon-picker-input", widget.attrs["class"])

    def test_widget__renders_input_preview_and_panel(self):
        """The widget renders the named input, a live preview of the current icon,
        and the picker container."""
        html = FontAwesomeIconPickerWidget().render("rank-icon", "star")
        self.assertIn('name="rank-icon"', html)
        self.assertIn("fa-icon-picker", html)
        self.assertIn("fa-icon-picker-input", html)
        # the preview addon reflects the current value
        self.assertIn("fa fa-fw fa-star", html)

    def test_widget__empty_value_renders_no_stray_icon(self):
        """With no value the preview is a bare icon (no trailing "fa-")."""
        html = FontAwesomeIconPickerWidget().render("rank-icon", "")
        self.assertIn("fa-icon-picker-preview", html)
        self.assertNotIn("fa-fw fa-\"", html)


class RankCreateViewIconPickerTest(ByteDeckTenantTestCase):
    """The rank add page serves the picker and its assets, and a bare name posts through."""

    def setUp(self):
        """A staff user, since rank editing is staff-only."""
        self.teacher = baker.make(User, is_staff=True, is_active=True)
        self.client.force_login(self.teacher)

    def test_rank_create__renders_picker_and_media(self):
        """The page includes the picker markup and loads the shared icon list + picker JS."""
        response = self.client.get(reverse("courses:rank_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fa-icon-picker")
        self.assertContains(response, "js/fa_icons_4.7.0.js")
        self.assertContains(response, "js/fa_icon_picker.js")

    def test_rank_create__stores_bare_name_and_modifiers(self):
        """Posting a bare name and a modifier stores them split, and they compose back."""
        data = {"name": "Picker Rank", "xp": 42, "fa_icon": "rocket", "fa_icon_modifiers": "fa-rotate-90"}
        response = self.client.post(reverse("courses:rank_create"), data=data)
        self.assertRedirects(response, reverse("courses:ranks"))
        rank = Rank.objects.get(name="Picker Rank")
        self.assertEqual(rank.fa_icon, "rocket")
        self.assertEqual(rank.fa_icon_modifiers, "fa-rotate-90")
        self.assertEqual(rank.fa_icon_class, "fa fa-rocket fa-rotate-90")


class NotifyRankUpIconTest(ByteDeckTenantTestCase):
    """The rank-up notification builds its icon from the rank's composed class,
    with no doubled 'fa' (the wrapper adds only colour/sizing)."""

    def test_notify_rank_up__icon_has_no_doubled_fa(self):
        """A promotion notification's icon HTML contains the rank's full class list
        exactly once, not the old 'fa fa-lg fa-fw fa fa-...' doubling."""
        from notifications.models import Notification, notify_rank_up

        Rank.objects.all().delete()
        baker.make(Rank, name="Low", xp=0, fa_icon="circle-o", fa_icon_modifiers="")
        baker.make(Rank, name="High", xp=100, fa_icon="forward", fa_icon_modifiers="fa-rotate-270")
        user = baker.make(User)

        notify_rank_up(user, old_xp=0, new_xp=100)

        notification = Notification.objects.filter(recipient=user, verb="promoted you to").latest("timestamp")
        self.assertIn("fa fa-forward fa-rotate-270", notification.font_icon)
        self.assertNotIn("fa fa-lg fa-fw fa fa-", notification.font_icon)
