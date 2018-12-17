from django.contrib import admin

# Register your models here.
from utilities.models import ImageResource, MenuItem, VideoResource


class ImageResourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'image', 'height', 'width', 'datetime_created', 'datetime_last_edit')


class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('label', 'sort_order', 'visible')


class VideoResourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'video_file')


admin.site.register(ImageResource, ImageResourceAdmin)
admin.site.register(MenuItem, MenuItemAdmin)
admin.site.register(VideoResource, VideoResourceAdmin)
