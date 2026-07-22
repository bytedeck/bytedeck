from django.db import connection

from django_tenants.utils import get_public_schema_name

from siteconfig.models import SiteConfig


def config(request):
    """
    Simple context processor that puts the config into every
    RequestContext, except those coming from the public schema,
    which doesn't include the config app.
        TEMPLATE_CONTEXT_PROCESSORS = (
            # ...
            'siteconfig.context_processors.config',
        )
    """
    if connection.schema_name != get_public_schema_name():
        return {"config": SiteConfig.get()}
    return {"config": None}


def deck_status(request):
    """Expose the current deck's Tenant row and public subscribe URL to templates.

    Powers the deck status banner in base.html (trial / expiring / over-limit /
    suspended, epic #1729). `current_deck` is None on the public and shared-library
    schemas, which also suppresses the banner entirely.
        TEMPLATE_CONTEXT_PROCESSORS = (
            # ...
            'hackerspace_online.context_processors.deck_status',
        )
    """
    from tenant.utils import get_current_deck, get_public_subscribe_url

    deck = get_current_deck()
    if deck is None:
        return {"current_deck": None}
    return {"current_deck": deck, "deck_subscribe_url": get_public_subscribe_url()}
