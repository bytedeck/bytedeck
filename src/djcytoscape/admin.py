from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from .models import CytoScape, CytoStyleSet, CytoStyleClass


class CytoScapeAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    fields = [
        'name',
        'initial_content_type', 'initial_object_id',
        'parent_scape',
        'style_set',
        'is_the_primary_scape',
        'autobreak'
    ]

    autocomplete_lookup_fields = {
        'generic': [
            ['initial_content_type', 'initial_object_id'], 
        ],
    }


class CytoStyleSetAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


class CytoStyleClassAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


admin.site.register(CytoScape, CytoScapeAdmin)
admin.site.register(CytoStyleSet, CytoStyleSetAdmin)
admin.site.register(CytoStyleClass, CytoStyleClassAdmin)
