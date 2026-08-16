import os

from django import template
from django.forms import FileField
from django.utils.safestring import mark_safe

register = template.Library()


# @register.filter
# def content_type(obj):
#     if not obj:
#         return False
#     return ContentType.objects.get_for_model(obj)


@register.filter
def filename(value: FileField):
    """Accepts a FileField object and returns the file's name.

    Callers render this without ``|safe``: the name comes from an uploaded file, so it is left
    for autoescaping, and only the fixed marker shown when the file has gone missing from
    storage is marked safe for its warning icon.
    """
    try:
        return os.path.basename(value.file.name)
    except FileNotFoundError:
        return mark_safe('<i class="fa fa-exclamation-triangle text-warning"></i> [File Missing]')
