import functools

from django.db import connection
from django.http import Http404
from django.shortcuts import redirect
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView

from tenant_schemas.utils import get_public_schema_name

from .models import Tenant
from .forms import TenantForm


def public_only_view(f):
    """A decorator that causes a view to raise Http404() if it is accessed by a non-public tenant"""
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if connection.schema_name == get_public_schema_name():
            return f(*args, **kwargs)
        else:
            raise Http404()
    return wrapper


class PublicOnlyViewMixin:
    """A mixin that causes a view to raise Http404() if it is accessed by a non-public tenant"""
    @method_decorator(public_only_view)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


def allow_non_public_view(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        request = args[0]
        if connection.schema_name != get_public_schema_name():
            return f(*args, **kwargs)
        elif request.path == '/':
            # TEMPORARY: redirect home page of the public tenant to admin site until we create a landing page.
            # return render(request, "index.html", {})
            return redirect('decks:new')

        raise Http404("Page not found!")
    return wrapper


class AllowNonPublicViewMixin:

    @method_decorator(allow_non_public_view)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class TenantCreate(PublicOnlyViewMixin, CreateView):
    model = Tenant
    form_class = TenantForm
    template_name = 'tenant/tenant_form.html'
