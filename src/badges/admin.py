from django.contrib import admin

# Register your models here.
from prerequisites.admin import PrereqInline

from .models import Badge, BadgeType, BadgeSeries

class BadgeTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order', 'fa_icon' )


class BadgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'xp','active')
    inlines = [
        PrereqInline,
    ]

admin.site.register(Badge, BadgeAdmin)
admin.site.register(BadgeSeries)
admin.site.register(BadgeType, BadgeTypeAdmin)
