from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin
from .models import Announcement


# Register your models here.


class AnnouncementAdmin(SummernoteModelAdmin):
    None


admin.site.register(Announcement, AnnouncementAdmin)
