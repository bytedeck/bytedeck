from django.contrib import admin

# Register your models here.
from import_export import resources
from import_export.admin import ImportExportActionModelAdmin

from prerequisites.admin import PrereqInline

from .models import Badge, BadgeType, BadgeSeries, BadgeAssertion, BadgeRarity


class BadgeRarityAdmin(admin.ModelAdmin):
    list_display = ('name', 'percentile', 'color', 'fa_icon')


class BadgeAssertionAdmin(admin.ModelAdmin):
    list_display = ('badge', 'user', 'ordinal', 'timestamp')


class BadgeTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order', 'fa_icon')


class BadgeResource(resources.ModelResource):
    class Meta:
        model = Badge
        exclude = ('xp',)


class BadgeAdmin(ImportExportActionModelAdmin):
    resource_class = BadgeResource
    list_display = ('name', 'xp', 'active')
    inlines = [
        PrereqInline,
    ]


admin.site.register(Badge, BadgeAdmin)
admin.site.register(BadgeSeries)
admin.site.register(BadgeRarity, BadgeRarityAdmin)
admin.site.register(BadgeType, BadgeTypeAdmin)
admin.site.register(BadgeAssertion, BadgeAssertionAdmin)
