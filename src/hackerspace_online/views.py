from django.shortcuts import render, redirect

from django.views.generic.base import RedirectView

from django.db import connection

from tenant_schemas.utils import get_public_schema_name


from tenant.views import allow_non_public_view, AllowNonPublicViewMixin
from siteconfig.models import SiteConfig


@allow_non_public_view
def home(request):
    print(connection.schema_name)
    if connection.schema_name == get_public_schema_name():
        # this isn't actually used because the decorator redirects before this code is called.
        return landing(request)
    else:
        if request.user.is_staff:
            return redirect('quests:approvals')

        if request.user.is_authenticated:
            return redirect('quests:quests')

        return redirect('account_login')


@allow_non_public_view
def simple(request):
    return render(request, "secret.html", {})


class FaviconRedirectView(AllowNonPublicViewMixin, RedirectView):
    permanent = True

    def get_redirect_url(self, *args, **kwargs):
        return SiteConfig.get().get_favicon_url()


def landing(request):
    return render(request, "index.html", {})
