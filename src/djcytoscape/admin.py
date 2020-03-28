from django.contrib import admin
from django.db import connection

from .models import CytoScape, CytoStyleSet, CytoStyleClass

if connection.schema_name != 'public':
    admin.site.register(CytoScape)
    admin.site.register(CytoStyleSet)
    admin.site.register(CytoStyleClass)
