from django.contrib import admin

# Register your models here.
from utilities.models import ImageResource, MenuItem


class ImageResourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'image', 'height', 'width', 'datetime_created', 'datetime_last_edit')


class MenuItemAdmin(admin.ModelAdmin):
    list_display = ('label', 'sort_order', 'visible')

admin.site.register(ImageResource, ImageResourceAdmin)
admin.site.register(MenuItem, MenuItemAdmin)