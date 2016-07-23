from django.contrib import admin

# Register your models here.
from .models import Tour, Step


class StepInline(admin.StackedInline):
    model = Step


class TourAdmin(admin.ModelAdmin):
    inlines = [
        StepInline,
    ]
    list_display = ('name', 'active')


admin.site.register(Tour, TourAdmin)
