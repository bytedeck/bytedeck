from django.contrib import admin

from .models import CytoScape, CytoStyleSet, CytoStyleClass

admin.site.register(CytoScape)
admin.site.register(CytoStyleSet)
admin.site.register(CytoStyleClass)
