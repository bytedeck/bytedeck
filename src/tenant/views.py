import functools

from django.core.mail import EmailMultiAlternatives
from django.template.loader import get_template
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.sites.models import Site
from django.db import connection
from django.dispatch import receiver
from django.http import Http404, HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.views.generic.edit import CreateView
from django.urls import reverse_lazy

from django_tenants.utils import get_public_schema_name
from django_tenants.utils import tenant_context

from allauth.account.utils import user_username, send_email_confirmation
from allauth.account.signals import email_confirmed
from allauth.account.models import EmailConfirmationHMAC

from siteconfig.models import SiteConfig
from utilities.html import textify

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


def generate_default_owner_password(user, tenant):
    """Generate a default password for a new deck's owner to"
    firstname-deckname-lastname
    """
    return "-".join([user.first_name, tenant.name, user.last_name]).lower()


class TenantCreate(PublicOnlyViewMixin, LoginRequiredMixin, CreateView):
    model = Tenant
    form_class = TenantForm
    template_name = 'tenant/tenant_form.html'
    login_url = reverse_lazy('admin:login')

    def form_valid(self, form):
        """ Copy the tenant name to the schema_name and the domain_url fields."""
        # TODO: this is duplication of code in admin.py.  Move this into the Tenant model?  Perhaps as a pre-save hook?
        form.instance.schema_name = form.instance.name.replace('-', '_')
        form.instance.domain_url = f'{form.instance.name}.{Site.objects.get(id=1).domain}'

        # save the form and get the response (HttpResponseRedirect)
        response = super().form_valid(form)

        # saved object (tenant) can be accessed via `object` attribute
        cleaned_data = form.cleaned_data
        with tenant_context(self.object):
            owner = SiteConfig.get().deck_owner

            # otherwise save first / last name
            owner.first_name = cleaned_data['first_name']
            owner.last_name = cleaned_data['last_name']
            owner.save()

            # set the owner's username to firstname.lastname (instead of "owner")
            user_username(owner, f"{owner.first_name}.{owner.last_name}")

            # set the owner's password to firstname-deckname-lastname
            owner.set_password(generate_default_owner_password(owner, self.object))

            # save email address
            email = cleaned_data['email']
            owner.email = email
            owner.save()

            return HttpResponseRedirect(self.get_success_url())

        return response

    def post(self, request, *args, **kwargs):
        """
        Handle POST requests: instantiate a form instance with the passed
        POST variables and then check if it's valid.
        """
        self.object = None

        form = self.get_form()
        if form.is_valid():
            # get the response (HttpResponseRedirect)...
            response = self.form_valid(form)
            # ...and send email confirmation message
            with tenant_context(self.object):
                owner = SiteConfig.get().deck_owner
                send_email_confirmation(
                    request=request,
                    user=owner,
                    signup=False,
                    email=owner.email,
                )

            return response
        else:
            return self.form_invalid(form)

    def get_success_url(self):
        """ Redirect to the newly created tenant."""
        return self.object.get_root_url()


@receiver(email_confirmed, sender=EmailConfirmationHMAC)
def email_confirmed_handler(email_address, **kwargs):
    """Send a welcome email to the deck owner after their email has been verified.
    Include instructions for how to log in with the username and password.
    """
    user = email_address.user
    config = SiteConfig.get()
    tenant = Tenant.get()

    # just verified email for a first time and never been logged into app before
    if user.last_login is not None:
        return
    # somehow user is not a deck owner
    if not (user.pk == config.deck_owner.pk):
        return

    subject = get_template("tenant/email/welcome_subject.txt").render(context={
        "config": config,
        "tenant": tenant,
        "user": user,
    })
    # email subject *must not* contain newlines
    subject = "".join(subject.splitlines())

    # generate "welcome" email for new user
    msg = get_template("tenant/email/welcome_message.txt").render(context={
        "config": config,
        "tenant": tenant,
        "user": user,
        "password": generate_default_owner_password(user, config.tenant),
    })

    # sending a text and HTML content combination
    email = EmailMultiAlternatives(
        subject,
        body=textify(msg),  # convert msg to plain text, using textify utility
        to=[user.email],
    )
    email.attach_alternative(msg, "text/html")
    email.send()
