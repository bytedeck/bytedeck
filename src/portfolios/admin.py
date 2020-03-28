from django.contrib import admin
from django.db import connection

from portfolios.models import Portfolio

if connection.schema_name != 'public':
    admin.site.register(Portfolio)
