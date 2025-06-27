from allauth.account.utils import send_email_confirmation, user_username
from django.contrib.sites.models import Site
from django_tenants.utils import tenant_context

from siteconfig.models import SiteConfig
from tenant.views import generate_default_owner_password
from .models import Tenant


def get_root_url():
    """
    Returns the root url of the currently connected tenant in the form of:
    scheme://[subdomain.]domain[.topleveldomain][:port]

    Port 8000 is hard coded for development

    Examples:
    - "hackerspace.bytedeck.com"
    - "hackerspace.localhost:8000"
    """
    return Tenant.get().get_root_url()


def generate_schema_name(tenant_name):
    return tenant_name.replace('-', '_').lower()


def setup_new_deck(
    *,
    tenant_name,
    owner_first_name,
    owner_last_name,
    owner_email,
    trial_end_date=None,
    stripe_customer_id=None,
    stripe_subscription_id=None,
    request=None,

):
    tenant = Tenant(
        name=tenant_name,
        schema_name=generate_schema_name(tenant_name),
        trial_end_date=trial_end_date,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
    )
    tenant.save()

    tenant.domain_url = f"{tenant_name}.{Site.objects.get(id=1).domain}",

    with tenant_context(tenant):
        owner = SiteConfig.get().deck_owner
        owner.first_name = owner_first_name
        owner.last_name = owner_last_name
        owner.email = owner_email
        # set the owner's username to firstname.lastname (instead of "owner")
        user_username(owner, f"{owner.first_name}.{owner.last_name}")

        # set the owner's password to firstname-deckname-lastname
        owner.set_password(generate_default_owner_password(owner, tenant))
        owner.save()

        if request is not None:
            send_email_confirmation(
                request=request,
                user=owner,
                signup=False,
                email=owner.email,
            )

    return tenant
