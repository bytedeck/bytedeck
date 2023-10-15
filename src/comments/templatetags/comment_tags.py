import os

from django import template
from django.forms import FileField

register = template.Library()


# @register.filter
# def content_type(obj):
#     if not obj:
#         return False
#     return ContentType.objects.get_for_model(obj)


@register.filter
def filename(value: FileField):
    """Acceipts a FileField object and returns the file's name."""
    try:
        return os.path.basename(value.file.name)
    except FileNotFoundError:
        return '<i class="fa fa-exclamation-triangle text-warning"></i> [File Missing]'
