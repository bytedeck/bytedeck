from django.contrib.auth import get_user_model

from model_bakery import baker

from courses.models import CourseStudent, MarkRange
from courses.templatetags.courses_tags import color_style_from_mark
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

User = get_user_model()


class ColorStyleFromMarkTagTest(ByteDeckTenantTestCase):
    """Tests for the color_style_from_mark template tag."""

    def test_returns_empty_string_when_no_mark_range(self):
        """A user not enrolled in any course has no mark range, so the tag returns ''."""
        user = baker.make(User)
        self.assertEqual(color_style_from_mark(user), "")

    def test_returns_light_color_for_light_theme(self):
        """When a mark range applies and the user is on the light theme, its light color is used."""
        MarkRange.objects.all().delete()
        MarkRange.objects.create(name="Range", minimum_mark=0.0, color_light='#111111', color_dark='#222222')

        user = baker.make(User)
        user.profile.dark_theme = False
        user.profile.mark_cached = 90.0
        user.profile.save()
        baker.make(CourseStudent, user=user, semester=SiteConfig.get().active_semester)

        style = color_style_from_mark(user)
        self.assertIn('#111111', style)
        self.assertNotIn('#222222', style)

    def test_returns_dark_color_for_dark_theme(self):
        """When a mark range applies and the user is on the dark theme, its dark color is used."""
        MarkRange.objects.all().delete()
        MarkRange.objects.create(name="Range", minimum_mark=0.0, color_light='#111111', color_dark='#222222')

        user = baker.make(User)
        user.profile.dark_theme = True
        user.profile.mark_cached = 90.0
        user.profile.save()
        baker.make(CourseStudent, user=user, semester=SiteConfig.get().active_semester)

        style = color_style_from_mark(user)
        self.assertIn('#222222', style)
        self.assertNotIn('#111111', style)
