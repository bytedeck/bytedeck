from django import template
from courses.models import MarkRange

register = template.Library()


@register.simple_tag(takes_context=True)
def mark_color(context):
    mark_range = MarkRange.objects.get_range_for_user(context.user)
    if mark_range:
        return mark_range.color
    else:
        return None
