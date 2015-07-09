from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin

# Register your models here.
from .models import Quest

class QuestAdmin(SummernoteModelAdmin):
    None

admin.site.register(Quest, QuestAdmin)
