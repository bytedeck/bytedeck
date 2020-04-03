from django.contrib import admin

from .models import CytoScape, CytoStyleSet, CytoStyleClass


class CytoScapeAdmin(admin.ModelAdmin):
    autocomplete_lookup_fields = {
        'generic': [
            ['initial_content_type', 'initial_object_id'], 
        ],
    }


admin.site.register(CytoScape, CytoScapeAdmin)
admin.site.register(CytoStyleSet)
admin.site.register(CytoStyleClass)
