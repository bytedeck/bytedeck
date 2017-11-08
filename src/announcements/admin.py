from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from .models import Announcement


# Register your models here.


class AnnouncementAdmin(SummernoteModelAdmin):
    list_display = ('title', 'datetime_released', )
    list_filter = ['datetime_released']
    search_fields = ['title', 'content', ]


admin.site.register(Announcement, AnnouncementAdmin)
