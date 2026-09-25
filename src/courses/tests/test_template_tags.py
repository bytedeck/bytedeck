from django.contrib.auth import get_user_model

from model_bakery import baker

from courses.models import CourseStudent, MarkRange
from courses.templatetags.courses_tags import color_style_from_mark
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

User = get_user_model()


class ColorStyleFromMarkTagTest(ByteDeckTenantTestCase):
    """Tests for the color_style_from_mark template tag."""

    def test_color_style_from_mark__empty_string_when_no_mark_range(self):
        """A user not enrolled in any course has no mark range, so the tag returns ''."""
        user = baker.make(User)
        self.assertEqual(color_style_from_mark(user), "")

    def test_color_style_from_mark__light_color_for_light_theme(self):
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

    def test_color_style_from_mark__dark_color_for_dark_theme(self):
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

    def _student_in(self, mark):
        """A student on the light theme, registered in the active semester, whose cached mark is ``mark``.

        Args:
            mark (float): the student's mark as a percentage.

        Returns:
            User: the student.
        """
        user = baker.make(User)
        baker.make(CourseStudent, user=user, semester=SiteConfig.get().active_semester)
        # Saving a registration recalculates the cached mark from the student's XP, so the mark
        # is set once they are registered.
        user.profile.dark_theme = False
        user.profile.mark_cached = mark
        user.profile.save()
        return user

    def test_color_style_from_mark__no_color_for_a_range_kept_out_of_headers(self):
        """A range with "Use this color in student headers" unchecked colors no header: it only
        appears on the Mark Calculations graph."""
        MarkRange.objects.all().delete()
        MarkRange.objects.create(
            name="Range", minimum_mark=0.0, color_light='#111111', color_dark='#222222', color_headers=False
        )

        self.assertEqual(color_style_from_mark(self._student_in(90.0)), "")

    def test_color_style_from_mark__a_lower_range_does_not_stand_in(self):
        """A student whose range is kept out of headers gets no color, not that of a lower range
        that is in them. With only the lowest range coloring headers, as a warning, a student well
        above it would otherwise be shown the warning."""
        MarkRange.objects.all().delete()
        MarkRange.objects.create(name="Pass", minimum_mark=50.0, color_light='#FF0000', color_dark='#FF0000')
        MarkRange.objects.create(
            name="A", minimum_mark=85.0, color_light='#00FF00', color_dark='#00FF00', color_headers=False
        )

        self.assertEqual(color_style_from_mark(self._student_in(90.0)), "")
        self.assertIn('#FF0000', color_style_from_mark(self._student_in(60.0)))
