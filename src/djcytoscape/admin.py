from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from .models import CytoScape, CytoStyleSet, CytoStyleClass


class CytoScapeAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


class CytoStyleSetAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


class CytoStyleClassAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


admin.site.register(CytoScape, CytoScapeAdmin)
admin.site.register(CytoStyleSet, CytoStyleSetAdmin)
admin.site.register(CytoStyleClass, CytoStyleClassAdmin)
