from django import template
from django.db import connection

from django_tenants.utils import get_public_schema_name

register = template.Library()


def _is_public_schema():
    return connection.schema_name == get_public_schema_name()


@register.simple_tag()
def is_public_schema():
    return _is_public_schema()
