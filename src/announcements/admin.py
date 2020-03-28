from django.contrib import admin
from django.db import connection

from django_summernote.admin import SummernoteModelAdmin

from .models import Announcement


class AnnouncementAdmin(SummernoteModelAdmin):
    list_display = ('title', 'datetime_released',)
    list_filter = ['datetime_released']
    search_fields = ['title', 'content', ]
    summernote_fields = ('content',)


if connection.schema_name != 'public':
    admin.site.register(Announcement, AnnouncementAdmin)
