from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from .models import Comment, Document


class CommentAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ['id', '__str__', 'text']

    class Meta:
        model = Comment


admin.site.register(Comment, CommentAdmin)
admin.site.register(Document)
