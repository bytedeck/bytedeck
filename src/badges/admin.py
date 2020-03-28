from django.contrib import admin
from django.db import connection

from import_export import resources
from import_export.admin import ImportExportActionModelAdmin

from prerequisites.admin import PrereqInline
from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin

from .models import Badge, BadgeType, BadgeSeries, BadgeAssertion, BadgeRarity


class BadgeRarityAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('name', 'percentile', 'color', 'fa_icon')


class BadgeAssertionAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('badge', 'user', 'ordinal', 'timestamp')


class BadgeTypeAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('name', 'sort_order', 'fa_icon')


class BadgeResource(NonPublicSchemaOnlyAdminAccessMixin, resources.ModelResource):
    class Meta:
        model = Badge
        exclude = ('xp',)


class BadgeAdmin(NonPublicSchemaOnlyAdminAccessMixin, ImportExportActionModelAdmin):
    resource_class = BadgeResource
    list_display = ('name', 'xp', 'active')
    inlines = [
        PrereqInline,
    ]


class BadgeSeriesAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


admin.site.register(Badge, BadgeAdmin)
admin.site.register(BadgeType, BadgeTypeAdmin)
admin.site.register(BadgeSeries, BadgeSeriesAdmin)
admin.site.register(BadgeRarity, BadgeRarityAdmin)
admin.site.register(BadgeAssertion, BadgeAssertionAdmin)
