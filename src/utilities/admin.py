from django.contrib import admin

# Register your models here.
from utilities.models import ImageResource


class ImageResourceAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'image', 'height', 'width', 'datetime_created', 'datetime_last_edit')

admin.site.register(ImageResource, ImageResourceAdmin)