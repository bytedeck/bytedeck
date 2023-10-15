from django.contrib import admin
from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from taggit.admin import TagAdmin
from taggit.models import Tag


class TagAdminTenantAware(NonPublicSchemaOnlyAdminAccessMixin, TagAdmin):
    pass


# remove default registration because we don't want Tags in the public Tenant
admin.site.unregister(Tag)
admin.site.register(Tag, TagAdminTenantAware)
