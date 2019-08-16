from django import template
from courses.models import MarkRange

register = template.Library()


@register.simple_tag(takes_context=True)
def color_style_from_mark(context):
    """ This should go in the style tag: style="{}"
    """
    mark_range = MarkRange.objects.get_range_for_user(context.request.user)
    if mark_range:
        return "background-image: None; background-color: {}".format(mark_range.color)
    else:
        return ""
