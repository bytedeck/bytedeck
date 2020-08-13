from django.shortcuts import render, redirect
from django.views.generic.base import RedirectView

from tenant.views import non_public_only_view, NonPublicOnlyViewMixin
from siteconfig.models import SiteConfig


@non_public_only_view
def home(request):
    """Public view never reaches here.  See non_public_only_view decorator/mixin for redirection for public tenant
    """
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


def landing(request):
    return render(request, "index.html", {})
