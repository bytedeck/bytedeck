from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from .models import Notification
from .tasks import delete_old_notifications


class NotificationAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    actions = ["delete_old_notifications_action"]

    def delete_old_notifications_action(self, request, queryset):
        """Admin action to delete notifications older than 90 days."""
        result = delete_old_notifications()
        self.message_user(request, result)

    delete_old_notifications_action.short_description = "Delete all notifications older than 90 days"


admin.site.register(Notification, NotificationAdmin)
