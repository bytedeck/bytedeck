from django.contrib import admin
from django.db import connection

from .models import Notification

if connection.schema_name != 'public':
    admin.site.register(Notification)
