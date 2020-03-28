import functools

from django.http import Http404
from django.db import connection

from tenant_schemas.utils import get_public_schema_name


def allow_non_public_view(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if connection.schema_name != get_public_schema_name():
            return f(*args, **kwargs)
        raise Http404("Page not found!")

    return wrapper


class AllowNonPublicViewMixin:
    def dispatch(self, *args, **kwargs):
        if connection.schema_name != get_public_schema_name():
            return super().dispatch(*args, **kwargs)
        raise Http404("Page not found!")
