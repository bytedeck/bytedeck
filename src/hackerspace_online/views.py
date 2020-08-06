from django.shortcuts import render, redirect
from django.views.generic.base import RedirectView

from tenant.views import allow_non_public_view, AllowNonPublicViewMixin
from siteconfig.models import SiteConfig


@allow_non_public_view
def home(request):
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
