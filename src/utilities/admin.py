from django.contrib import admin
from django.contrib.flatpages.models import FlatPage
from django.contrib.flatpages.admin import FlatPageAdmin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from bytedeck_summernote.admin import ByteDeckSummernoteAdvancedModelAdmin

from .models import ImageResource, MenuItem, VideoResource


class FlatPageAdmin2(FlatPageAdmin, ByteDeckSummernoteAdvancedModelAdmin):
    list_display = ('url', 'title', 'registration_required',)
    summernote_fields = ('content',)


admin.site.unregister(FlatPage)
admin.site.register(FlatPage, FlatPageAdmin2)


class ImageResourceAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'image', 'height', 'width', 'datetime_created', 'datetime_last_edit')


class MenuItemAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('label', 'sort_order', 'visible')


class VideoResourceAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('id', 'title', 'video_file')


admin.site.register(MenuItem, MenuItemAdmin)
admin.site.register(ImageResource, ImageResourceAdmin)
admin.site.register(VideoResource, VideoResourceAdmin)
