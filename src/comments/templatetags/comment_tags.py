import os

from django import template
from django.contrib.contenttypes.models import ContentType

register = template.Library()


@register.filter
def content_type(obj):
    if not obj:
        return False
    return ContentType.objects.get_for_model(obj)


@register.filter
def filename(value):
    return os.path.basename(value.file.name)
