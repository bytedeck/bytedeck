from django.contrib import admin

from .models import Prereq
# Register your models here.

class PrereqAdmin(admin.ModelAdmin):
    list_display = ('id','parent', '__str__',)


admin.site.register(Prereq, PrereqAdmin)
