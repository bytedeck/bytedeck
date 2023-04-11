from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from bytedeck_summernote.admin import ByteDeckSummernoteSafeModelAdmin

from .models import Announcement


class AnnouncementAdmin(NonPublicSchemaOnlyAdminAccessMixin, ByteDeckSummernoteSafeModelAdmin):
    list_display = ('title', 'datetime_released',)
    list_filter = ['datetime_released']
    search_fields = ['title', 'content', ]
    summernote_fields = ('content',)


admin.site.register(Announcement, AnnouncementAdmin)
