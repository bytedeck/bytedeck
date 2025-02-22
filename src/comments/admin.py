from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from .models import Comment, Document


class CommentAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ['id', '__str__', 'text']
    autocomplete_fields = ("parent",)
    search_fields = ("text",)

    class Meta:
        model = Comment


class DocumentAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    autocomplete_fields = ("comment",)

    class Meta:
        model = Document


admin.site.register(Comment, CommentAdmin)
admin.site.register(Document, DocumentAdmin)
