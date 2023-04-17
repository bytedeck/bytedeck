from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from .models import CytoScape


class CytoScapeAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    fields = [
        'name',
        'initial_content_type', 'initial_object_id',
        'parent_scape',
        'is_the_primary_scape',
        'autobreak'
    ]

    autocomplete_lookup_fields = {
        'generic': [
            ['initial_content_type', 'initial_object_id'],
        ],
    }


admin.site.register(CytoScape, CytoScapeAdmin)
