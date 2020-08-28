from django.contrib.messages.views import SuccessMessageMixin
from django.db import connection
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.views.generic.base import RedirectView
from django.views.generic.edit import FormView

from allauth.account.views import PasswordResetFromKeyView, PasswordResetView
from tenant_schemas.utils import get_public_schema_name

from siteconfig.models import SiteConfig
from tenant.views import PublicOnlyViewMixin, non_public_only_view

from .forms import CustomResetPasswordForm, PublicContactForm


def home(request):
    """
    For the public tenant: render the landing page.
    For non_public tenants: redirect to default pages based on who is authenticated
    """
    if connection.schema_name == get_public_schema_name():
        return LandingPageView.as_view()(request)

    else:  # Non public tenants
        if request.user.is_staff:
            return redirect('quests:approvals')

        if request.user.is_authenticated:
            return redirect('quests:quests')

        return redirect('account_login')


@non_public_only_view
def simple(request):
    return render(request, "secret.html", {})


class FaviconRedirectView(RedirectView):
    permanent = True

    def get_redirect_url(self, *args, **kwargs):
        # public
        if connection.schema_name == get_public_schema_name():
            return static('icon/favicon.ico')
        else:  # tenants
            return SiteConfig.get().get_favicon_url()


class LandingPageView(PublicOnlyViewMixin, SuccessMessageMixin, FormView):
    template_name = 'public/index.html'
    form_class = PublicContactForm

    def form_valid(self, form):
        # This method is called when valid form data has been POSTed.
        # It should return an HttpResponse.
        success = form.send_email()

        if success:
            self.success_message = "Thank you for contacting us!  We'll be in touch soon."
        else:
            self.success_message = "There was an error submitting the form.  Please try contacting us direct by email at <a href=\"mailto:contact@bytedeck.com\">contact@bytedeck.com</a>"  # noqa

        return super().form_valid(form)

    def get_success_url(self):
        return reverse('home')


class CustomPasswordResetView(PasswordResetView):

    form_class = CustomResetPasswordForm


class CustomPasswordResetFromKeyView(PasswordResetFromKeyView):
    success_url = reverse_lazy('account_login')


def landing(request):
    return render(request, "index.html", {})
