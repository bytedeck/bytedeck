from django import template
from django.contrib.auth import get_user_model
from courses.models import MarkRange

User = get_user_model()

register = template.Library()


@register.simple_tag()
def color_style_from_mark(user):
    """ This should go in the style tag: style="{}"
    """
    mark_range = MarkRange.objects.get_range_for_user(user)
    # A range can be kept out of headers, and then appears only on the Mark Calculations graph.
    # Its students get no color rather than a lower range's, which would misstate their mark.
    if mark_range and mark_range.color_headers:
        if user.profile.dark_theme:
            hex_color = mark_range.color_dark
        else:
            hex_color = mark_range.color_light

        return f"background-image: none !important; background-color: {hex_color} !important;"
    else:
        return ""
