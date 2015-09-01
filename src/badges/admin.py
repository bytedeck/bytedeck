from django.contrib import admin

# Register your models here.
from prerequisites.admin import PrereqInline

from .models import Badge, BadgeType, BadgeSeries

class BadgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'xp','visible_to_students')
    inlines = [
        PrereqInline,
    ]

admin.site.register(Badge, BadgeAdmin)
admin.site.register(BadgeSeries)
admin.site.register(BadgeType)
