from django.contrib import messages
from django.db import connection
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.views.generic.base import RedirectView

from allauth.account.views import PasswordResetFromKeyView, PasswordResetView
from django_tenants.utils import get_public_schema_name

from siteconfig.models import SiteConfig
from tenant.views import PublicOnlyViewMixin, NonPublicOnlyViewMixin, non_public_only_view

from .forms import CustomResetPasswordForm


def home(request):
    """
    For the public tenant: render the landing page.
    For non_public tenants: redirect to default pages based on who is authenticated
    """
    if connection.schema_name == get_public_schema_name():
        return LandingRedirectView.as_view()(request)

    else:  # Non public tenants
        if request.user.is_staff:
            # Warn staff, via a dismissable message, when the deck has no open semester so students
            # can't join a course — with a link to open one (issue #2060).
            if SiteConfig.get().has_no_open_semester():
                messages.warning(
                    request,
                    'This deck has no open semester, so students can’t join a course. '
                    f'<a href="{reverse("courses:semester_list")}">Create and activate a semester</a> to let them register.',
                    extra_tags='safe',
                )
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


class LandingRedirectView(PublicOnlyViewMixin, RedirectView):
    permanent = True

    def get_redirect_url(self, *args, **kwargs):
        return reverse('django.contrib.flatpages.views.flatpage', args=['home'])


# apply `NonPublicOnlyViewMixin` mixin, fix #1214
class CustomPasswordResetView(NonPublicOnlyViewMixin, PasswordResetView):

    form_class = CustomResetPasswordForm


# apply `NonPublicOnlyViewMixin` mixin, fix #1214
class CustomPasswordResetFromKeyView(NonPublicOnlyViewMixin, PasswordResetFromKeyView):
    success_url = reverse_lazy('account_login')
