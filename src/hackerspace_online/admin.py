from django.contrib import admin
from django.contrib.sites.models import Site
from django.contrib.flatpages.models import FlatPage
from django.contrib.flatpages.admin import FlatPageAdmin

from django_summernote.admin import SummernoteModelAdmin

from tenant.admin import PublicSchemaOnlyAdminAccessMixin


class FlatPageAdmin2(PublicSchemaOnlyAdminAccessMixin, FlatPageAdmin, SummernoteModelAdmin):
    list_display = ('url', 'title', 'registration_required',)


admin.site.unregister(FlatPage)
admin.site.register(FlatPage, FlatPageAdmin2)

admin.site.unregister(Site)


@admin.register(Site)
class SiteCustomAdmin(PublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('domain', 'name')
    search_fields = ('domain', 'name')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
