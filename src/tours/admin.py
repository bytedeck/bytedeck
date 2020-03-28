from django.contrib import admin
from django.db import connection

from .models import Tour, Step


class StepInline(admin.StackedInline):
    model = Step


class TourAdmin(admin.ModelAdmin):
    inlines = [
        StepInline,
    ]
    list_display = ('name', 'active')


if connection.schema_name != 'public':
    admin.site.register(Tour, TourAdmin)
