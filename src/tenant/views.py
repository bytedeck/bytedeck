import functools

from django.db import connection
from django.http import Http404
from django.shortcuts import render
from django.utils.decorators import method_decorator
from tenant_schemas.utils import get_public_schema_name


def allow_non_public_view(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        request = args[0]
        if connection.schema_name != get_public_schema_name():
            return f(*args, **kwargs)
        elif request.path == '/':
            # TEMPORARY: redirect home page of the public tenant to admin site until we create a landing page.
            return render(request, "index.html", {})

        raise Http404("Page not found!")
    return wrapper


class AllowNonPublicViewMixin:

    @method_decorator(allow_non_public_view)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)
