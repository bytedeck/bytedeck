from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from utilities.models import ImageResource, MenuItem, VideoResource


class ImageResourceAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'image', 'height', 'width', 'datetime_created', 'datetime_last_edit')


class MenuItemAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('label', 'sort_order', 'visible')


class VideoResourceAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('id', 'title', 'video_file')


admin.site.register(MenuItem, MenuItemAdmin)
admin.site.register(ImageResource, ImageResourceAdmin)
admin.site.register(VideoResource, VideoResourceAdmin)
