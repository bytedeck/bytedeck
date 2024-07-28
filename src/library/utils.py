import functools

from django.apps import apps
from django_tenants.utils import schema_context


def get_library_schema_name():
    return apps.get_app_config('library').TENANT_NAME


def from_library_schema_first(request):
    """
    Function to check if the POST request contains `use_schema` data which will allow us to
    use the library schema for fetching campaigns or quest data
    """

    current_schema_name = request.tenant.schema_name
    use_schema_name = request.POST.get('use_schema')
    schema_name = use_schema_name if use_schema_name else current_schema_name

    force_schema_func = functools.partial(schema_context, schema_name)

    return force_schema_func()


library_schema_context = functools.partial(schema_context, get_library_schema_name())
