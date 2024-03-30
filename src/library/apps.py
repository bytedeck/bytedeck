from django.apps import AppConfig
from django.conf import settings


class LibraryConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'library'

    TENANT_NAME = getattr(settings, 'LIBRARY_TENANT_NAME', 'library')
