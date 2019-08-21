from django import template
from courses.models import MarkRange

register = template.Library()


@register.simple_tag(takes_context=True)
def color_style_from_mark(context, using_dark_theme):
    """ This should go in the style tag: style="{}"
    """
    mark_range = MarkRange.objects.get_range_for_user(context.request.user)
    if mark_range:
        if using_dark_theme:
            hex_color = mark_range.color_dark
        else:
            hex_color = mark_range.color_light

        return "background-image: none; background-color: {};".format(hex_color)
    else:
        return ""
