from allauth.socialaccount.admin import SocialAccountAdmin, SocialAppAdmin

from django.contrib import admin
from django.contrib.auth.models import Group, User
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.sites.models import Site
from django.db import connection, router

from django_tenants.utils import get_public_schema_name

from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from allauth.account.models import EmailAddress

from django_summernote.models import Attachment

from tenant.admin import PublicSchemaOnlyAdminAccessMixin
from tenant.deletion import SchemaAwareCollector, schema_aware_get_deleted_objects


class SiteCustomAdmin(PublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('domain', 'name')
    search_fields = ('domain', 'name')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.unregister(Site)
admin.site.register(Site, SiteCustomAdmin)


class GroupCustomAdmin(PublicSchemaOnlyAdminAccessMixin, GroupAdmin):
    pass


admin.site.unregister(Group)
admin.site.register(Group, GroupCustomAdmin)


class SocialAppCustomAdmin(PublicSchemaOnlyAdminAccessMixin, SocialAppAdmin):
    pass


admin.site.unregister(SocialApp)
admin.site.register(SocialApp, SocialAppCustomAdmin)


class SocialAccountCustomAdmin(PublicSchemaOnlyAdminAccessMixin, SocialAccountAdmin):
    pass


admin.site.unregister(SocialAccount)
admin.site.register(SocialAccount, SocialAccountCustomAdmin)


class CustomUserAdmin(UserAdmin):
    """Django's default UserAdmin, but with schema-aware deletion.

    On the public schema, tenant-app tables (e.g. quest_manager_questsubmission)
    don't exist, so the default delete cascade fails with
    ``relation "..." does not exist`` (issue #691).  On the public schema we use
    the schema-aware collector, which skips those absent tables; on tenant
    schemas nothing changes (every table is present, so it's a no-op).
    """

    def _on_public_schema(self):
        return connection.schema_name == get_public_schema_name()

    def get_deleted_objects(self, objs, request):
        if not self._on_public_schema():
            return super().get_deleted_objects(objs, request)
        return schema_aware_get_deleted_objects(objs, request, self.admin_site)

    def delete_model(self, request, obj):
        if not self._on_public_schema():
            return super().delete_model(request, obj)
        collector = SchemaAwareCollector(using=router.db_for_write(obj.__class__, instance=obj))
        collector.collect([obj])
        collector.delete()

    def delete_queryset(self, request, queryset):
        if not self._on_public_schema():
            return super().delete_queryset(request, queryset)
        collector = SchemaAwareCollector(using=router.db_for_write(queryset.model))
        collector.collect(queryset)
        collector.delete()


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


# Remove a few more models from admin for now to simplify
admin.site.unregister(Attachment)
admin.site.unregister(SocialToken)
admin.site.unregister(EmailAddress)
