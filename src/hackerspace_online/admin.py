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
        """Return ``True`` when the current connection is on the public schema.

        The schema-aware deletion paths below only diverge from Django's default
        on the public schema; on tenant schemas every table exists so the
        default behaviour is correct.

        :returns: bool -- whether the active schema is the public schema.
        """
        return connection.schema_name == get_public_schema_name()

    def get_deleted_objects(self, objs, request):
        """Build the admin delete-confirmation data (schema-aware on public).

        On tenant schemas, defer to Django's default.  On the public schema,
        use :func:`schema_aware_get_deleted_objects` so the confirmation page
        doesn't query tenant-only tables that don't exist there (issue #691).

        :param objs: the objects queued for deletion.
        :param request: the current admin request.
        :returns: ``(to_delete, model_count, perms_needed, protected)`` -- the
            same 4-tuple Django's ``get_deleted_objects`` returns.
        """
        if not self._on_public_schema():
            return super().get_deleted_objects(objs, request)
        return schema_aware_get_deleted_objects(objs, request, self.admin_site)

    def delete_model(self, request, obj):
        """Delete a single user (schema-aware cascade on the public schema).

        On tenant schemas, defer to Django's default ``delete_model``.  On the
        public schema, delete via :class:`SchemaAwareCollector` so absent
        tenant-app tables are skipped instead of raising (issue #691).
        ``origin=obj`` mirrors ``Model.delete()`` so ``pre_delete``/
        ``post_delete`` receivers still see the triggering object.

        :param request: the current admin request.
        :param obj: the ``User`` instance to delete.
        """
        if not self._on_public_schema():
            return super().delete_model(request, obj)
        collector = SchemaAwareCollector(
            using=router.db_for_write(obj.__class__, instance=obj), origin=obj,
        )
        collector.collect([obj])
        collector.delete()

    def delete_queryset(self, request, queryset):
        """Bulk-delete users (schema-aware cascade on the public schema).

        On tenant schemas, defer to Django's default ``delete_queryset``.  On
        the public schema, delete via :class:`SchemaAwareCollector` so absent
        tenant-app tables are skipped instead of raising (issue #691).
        ``using=queryset.db`` and ``origin=queryset`` mirror ``QuerySet.delete()``
        so routing and ``pre_delete``/``post_delete`` receivers behave as usual.

        :param request: the current admin request.
        :param queryset: the ``User`` queryset selected for deletion.
        """
        if not self._on_public_schema():
            return super().delete_queryset(request, queryset)
        collector = SchemaAwareCollector(using=queryset.db, origin=queryset)
        collector.collect(queryset)
        collector.delete()


admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)


# Remove a few more models from admin for now to simplify
admin.site.unregister(Attachment)
admin.site.unregister(SocialToken)
admin.site.unregister(EmailAddress)
