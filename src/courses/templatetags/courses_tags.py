from django import template
from django.contrib.auth import get_user_model
from courses.models import MarkRange

User = get_user_model()

register = template.Library()


@register.simple_tag()
def color_style_from_mark(user):
    """The inline style that colors the header by the student's mark, for its style="" attribute.

    Only ranges that color student headers count: a student whose mark is in a range kept out of
    them gets the color of the next range below it that colors them.

    Args:
        user (User): the signed-in user whose header is being drawn.

    Returns:
        str: the CSS for that range's color in the user's theme, or an empty string when no range
        that colors headers applies to their mark.
    """
    mark_range = MarkRange.objects.get_range_for_user(user, headers_only=True)
    if mark_range:
        if user.profile.dark_theme:
            hex_color = mark_range.color_dark
        else:
            hex_color = mark_range.color_light

        return f"background-image: none !important; background-color: {hex_color} !important;"
    else:
        return ""
