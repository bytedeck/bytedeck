import functools

from django.apps import apps
from django_tenants.utils import schema_context


library_schema_context = functools.partial(schema_context, apps.get_app_config('library').TENANT_NAME)
