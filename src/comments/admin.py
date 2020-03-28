from django.contrib import admin
from django.db import connection

from .models import Comment, Document


class CommentAdmin(admin.ModelAdmin):
    list_display = ['id', '__str__', 'text']

    class Meta:
        model = Comment


if connection.schema_name != 'public':
    admin.site.register(Comment, CommentAdmin)
    admin.site.register(Document)
