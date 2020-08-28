from django.db import connection
from django.shortcuts import render, redirect
from django.views.generic.base import RedirectView

from tenant_schemas.utils import get_public_schema_name

from tenant.views import non_public_only_view, NonPublicOnlyViewMixin, public_only_view
from siteconfig.models import SiteConfig


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


class FaviconRedirectView(NonPublicOnlyViewMixin, RedirectView):
    permanent = True

    def get_redirect_url(self, *args, **kwargs):
        return SiteConfig.get().get_favicon_url()


@public_only_view
def landing(request):
    return render(request, "public/index.html", {})
