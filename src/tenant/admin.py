from django.conf import settings
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import connection
from tenant_schemas.utils import get_public_schema_name

from tenant.models import Tenant


class PublicSchemaOnlyAdminAccessMixin:
    def has_view_or_change_permission(self, request, obj=None):
        return connection.schema_name == get_public_schema_name()

    def has_add_permission(self, request):
        return connection.schema_name == get_public_schema_name()

    def has_module_permission(self, request):
        return connection.schema_name == get_public_schema_name()


class NonPublicSchemaOnlyAdminAccessMixin:
    def has_view_or_change_permission(self, request, obj=None):
        return connection.schema_name != get_public_schema_name()

    def has_add_permission(self, request):
        return connection.schema_name != get_public_schema_name()

    def has_module_permission(self, request):
        return connection.schema_name != get_public_schema_name()


class TenantAdmin(PublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('schema_name', 'domain_url', 'name', 'desc', 'created_on')

    def save_model(self, request, obj, form, change):
        obj.schema_name = obj.name.lower()
        obj.domain_url = "%s.%s" % (obj.schema_name, settings.WEB_URL)
        obj.save()


admin.site.register(Tenant, TenantAdmin)
