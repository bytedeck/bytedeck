from django.contrib import admin
from django.db import connection

from tenant.models import Tenant

if connection.schema_name == 'public':
    class TenantAdmin(admin.ModelAdmin):
        list_display = ('schema_name', 'domain_url', 'name', 'desc', 'created_on')


    admin.site.register(Tenant, TenantAdmin)
