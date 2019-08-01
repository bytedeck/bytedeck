from django.contrib import admin
from django.contrib.flatpages.admin import FlatPageAdmin
from django.contrib.flatpages.models import FlatPage
# Define a new FlatPageAdmin
from django_summernote.admin import SummernoteModelAdmin


class FlatPageAdmin2(FlatPageAdmin, SummernoteModelAdmin):
    list_display = ('url', 'title', 'registration_required',)


# Re-register FlatPageAdmin
admin.site.unregister(FlatPage)
admin.site.register(FlatPage, FlatPageAdmin2)
