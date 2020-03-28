from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from .models import Notification


class NotificationAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


admin.site.register(Notification, NotificationAdmin)
