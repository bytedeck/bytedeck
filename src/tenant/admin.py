from django.contrib import admin
from django.contrib.sites.models import Site
from django.db import connection
from django_tenants.utils import get_public_schema_name

from tenant.models import Tenant, TenantDomain


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


class TenantDomainInline(admin.TabularInline):
    model = TenantDomain
    extra = 1


class TenantAdmin(PublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('schema_name', 'domain_url', 'name', 'desc', 'created_on')
    exclude = ('domain_url', 'schema_name')
    inlines = [
        TenantDomainInline,
    ]

    def save_model(self, request, obj, form, change):
        if obj.name.lower() == "public":
            return
        if not change:
            obj.schema_name = obj.name.replace('-', '_').lower()
            obj.domain_url = "%s.%s" % (obj.name.lower(), Site.objects.get(id=1).domain)
        obj.save()


admin.site.register(Tenant, TenantAdmin)
