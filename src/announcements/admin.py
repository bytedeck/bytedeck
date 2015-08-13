from django.contrib import admin
from .models import Announcement
from django_summernote.admin import SummernoteModelAdmin

# Register your models here.

class AnnouncementAdmin(SummernoteModelAdmin):
    None

admin.site.register(Announcement, AnnouncementAdmin)
