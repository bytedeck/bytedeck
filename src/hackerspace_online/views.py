import json
import stripe
from datetime import datetime
from django.contrib.messages.views import SuccessMessageMixin
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.urls import reverse, reverse_lazy
from django.views.generic.base import RedirectView
from django.views.generic.edit import FormView
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from allauth.account.views import PasswordResetFromKeyView, PasswordResetView
from django_tenants.utils import get_public_schema_name

from siteconfig.models import SiteConfig
from tenant.utils import setup_new_deck
from tenant.views import PublicOnlyViewMixin, NonPublicOnlyViewMixin, non_public_only_view

from .forms import CustomResetPasswordForm, PublicContactForm


def home(request):
    """
    For the public tenant: render the landing page.
    For non_public tenants: redirect to default pages based on who is authenticated
    """
    if connection.schema_name == get_public_schema_name():
        return LandingRedirectView.as_view()(request)

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


class LandingRedirectView(PublicOnlyViewMixin, RedirectView):
    permanent = True

    def get_redirect_url(self, *args, **kwargs):
        return reverse('django.contrib.flatpages.views.flatpage', args=['home'])


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


# apply `NonPublicOnlyViewMixin` mixin, fix #1214
class CustomPasswordResetView(NonPublicOnlyViewMixin, PasswordResetView):

    form_class = CustomResetPasswordForm


# apply `NonPublicOnlyViewMixin` mixin, fix #1214
class CustomPasswordResetFromKeyView(NonPublicOnlyViewMixin, PasswordResetFromKeyView):
    success_url = reverse_lazy('account_login')


def landing(request):
    return render(request, "index.html", {})


@csrf_exempt
def stripe_webhook(request):
    webhook_secret = settings.STRIPE_WEBHOOK_SECRET
    request_data = json.loads(request.body)

    if webhook_secret:
        # Retrieve the event by verifying the signature using the raw body and secret if webhook signing is configured.
        signature = request.headers.get('stripe-signature')
        try:
            event = stripe.Webhook.construct_event(payload=request.body, sig_header=signature, secret=webhook_secret)
            data = event['data']
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)})
        # Get the type of webhook event sent - used to check the status of PaymentIntents.
        event_type = event['type']
    else:
        data = request_data['data']
        event_type = request_data['type']

    data_object = data['object']

    if event_type == 'checkout.session.completed':
        # print('🔔 Payment succeeded!')
        ...

    elif event_type == 'customer.subscription.trial_will_end':
        # print('Subscription trial will end')
        ...

    elif event_type == 'customer.subscription.created':
        # print('🔥 Subscription created %s', event.id)
        trial_end_date = None
        if data_object['status'] == 'trialing' and data_object.get('current_period_end'):
            trial_end_date = datetime.fromtimestamp(data_object['current_period_end'])

        setup_new_deck(
            tenant_name=data_object['metadata']['deck_name'],
            owner_first_name=data_object['metadata']['first_name'],
            owner_last_name=data_object['metadata']['last_name'],
            owner_email=data_object['metadata']['email'],
            trial_end_date=trial_end_date,
            stripe_subscription_id=data_object['id'],
            stripe_customer_id=data_object['customer'],
            request=request,
        )
    elif event_type == 'customer.subscription.updated':
        # print('Subscription updated %s', event.id)
        # TODO: Handle when customer decides to upgrade their subscription plan
        ...
    elif event_type == 'customer.subscription.deleted':
        # handle subscription canceled automatically based
        # upon your subscription settings. Or if the user cancels it.
        # print('Subscription canceled: %s', event.id)
        ...
    elif event_type == 'entitlements.active_entitlement_summary.updated':
        # handle active entitlement summary updated
        # print('Active entitlement summary updated: %s', event.id)
        ...

    return JsonResponse({'success': True, 'message': None})
