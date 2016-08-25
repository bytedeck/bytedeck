from django.contrib import admin
from portfolios.models import Artwork
from .models import Profile

# Register your models here.

admin.site.register(Profile)
admin.site.register(Artwork)
