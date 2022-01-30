import functools

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sites.models import Site
from django.db import connection
from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView

from django_tenants.utils import get_public_schema_name

from .forms import TenantForm
from .models import Tenant


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


def non_public_only_view(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if connection.schema_name != get_public_schema_name():
            return f(*args, **kwargs)
        raise Http404("Page not found!")
    return wrapper


class NonPublicOnlyViewMixin:

    @method_decorator(non_public_only_view)
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)


class TenantCreate(PublicOnlyViewMixin, LoginRequiredMixin, CreateView):
    model = Tenant
    form_class = TenantForm
    template_name = 'tenant/tenant_form.html'

    def form_valid(self, form):
        """ Copy the tenant name to the schema_name and the domain_url fields."""
        tenant = form.save(commit=False)
        # TODO: this is duplication of code in admin.py.  Move this into the Tenant model?  Perhaps as a pre-save hook?
        tenant.schema_name = tenant.name.replace('-', '_')
        tenant.domain_url = f"{tenant.name}.{Site.objects.get(id=1).domain}"
        return super().form_valid(form)

    def get_success_url(self):
        """ Redirect to the newly created tenant."""
        return self.object.get_root_url()
