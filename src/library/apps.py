from django.apps import AppConfig
from django.conf import settings


class LibraryConfig(AppConfig):
    """Django app config for the Shared Library.

    Also holds the name of the tenant schema the Library lives in, so the rest of the
    codebase asks the app registry for it instead of each caller reading the setting.
    A deployment that keeps its Library in another schema sets `LIBRARY_TENANT_NAME`.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'library'

    TENANT_NAME = getattr(settings, 'LIBRARY_TENANT_NAME', 'library')
