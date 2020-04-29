from django.db import connection

from .models import SiteConfig
from django_tenants.utils import get_public_schema_name


def config(request):
    """
    Simple context processor that puts the config into every
    RequestContext.
        TEMPLATE_CONTEXT_PROCESSORS = (
            # ...
            'siteconfig.context_processors.config',
        )
    """
    if connection.schema_name != get_public_schema_name():
        return {"config": SiteConfig.get()}
    return {"config": None}
