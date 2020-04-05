from django.contrib import admin

from .models import Tour, Step
from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin


class StepInline(admin.StackedInline):
    model = Step


class TourAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    inlines = [
        StepInline,
    ]
    list_display = ('name', 'active')


admin.site.register(Tour, TourAdmin)
