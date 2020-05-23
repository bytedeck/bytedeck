from django.db import connection

from siteconfig.models import SiteConfig
from tenant_schemas.utils import get_public_schema_name


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
