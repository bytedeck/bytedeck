import functools

from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sites.models import Site
from django.db import connection
from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView
from django_tenants.utils import get_public_schema_name

from django_tenants.utils import tenant_context

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
        from siteconfig.models import SiteConfig

        # TODO: this is duplication of code in admin.py.  Move this into the Tenant model?  Perhaps as a pre-save hook?

        # Because commit=False does not only result in not creating a record at the database.
        # It also has for example impact on many-to-many fields in the form.
        #
        # When you thus specify commit=False, the ManyToManyFields of the model that are also present in the form,
        # are not stored in the database either, since at that moment, no primary key for the object exists yet.
        #
        # One can of course implement the logic themselves, but the idea of a ModelForm is to remove as much
        # boilerplate code as possible.
        form.instance.schema_name = form.instance.name.replace('-', '_')
        form.instance.domain_url = f'{form.instance.name}.{Site.objects.get(id=1).domain}'

        # save the form and get the response (HttpResponseRedirect)
        response = super().form_valid(form)

        # saved object (tenant) can be accessed via `object` attribute
        cleaned_data = form.cleaned_data
        with tenant_context(self.object):
            owner = SiteConfig.get().deck_owner or None
            if owner is None:  # where is the owner?
                return response  # noqa

            # otherwise save first / last name
            owner.first_name = cleaned_data['first_name']
            owner.last_name = cleaned_data['last_name']
            owner.save()

            # save email address...
            email = cleaned_data['email']
            if len(email):
                owner.email = email
                owner.save()

            # ...and send email confirmation message
            from allauth.account.utils import send_email_confirmation
            if self.request and len(email):
                send_email_confirmation(
                    request=self.request,
                    user=owner,
                    signup=False,
                    email=owner.email,
                )

        return response

    def get_success_url(self):
        """ Redirect to the newly created tenant."""
        return self.object.get_root_url()
