from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db import connection
from django.shortcuts import render, redirect
from django.templatetags.static import static
from django.urls import reverse
from django.views.generic.edit import FormView
from django.views.generic.base import RedirectView

from tenant_schemas.utils import get_public_schema_name

from tenant.views import non_public_only_view, NonPublicOnlyViewMixin, public_only_view, PublicOnlyViewMixin
from siteconfig.models import SiteConfig

from .forms import PublicContactForm


def home(request):
    """
    For the public tenant: render thre landing page.
    For non_public tenants: render default pages based on who is authenticated
    """
    if connection.schema_name == get_public_schema_name():
        return landing(request)

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


@public_only_view
def landing(request):
    return render(request, "public/index.html", {})


class LandingPageView(PublicOnlyViewMixin, SuccessMessageMixin, FormView):
    template_name = 'public/index.html'
    form_class = PublicContactForm
    success_message = "Thank you for contacting us!  We'll be in touch soon."

    def form_valid(self, form):
        # This method is called when valid form data has been POSTed.
        # It should return an HttpResponse.
        success = form.send_email()

        if success:
            self.success_message = "Thank you for contacting us!  We'll be in touch soon."
        else:
            self.success_message = "ERROR"

        return super().form_valid(form)

    def get_success_url(self):
        return reverse('test')
