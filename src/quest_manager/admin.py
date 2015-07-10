from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin

# Register your models here.
from .models import Quest, Category, Prerequisite

class PrerequisiteInLine(admin.StackedInline):
    model = Prerequisite
    fk_name = "parent_quest"

class QuestAdmin(SummernoteModelAdmin):
    list_display = ('name', 'xp','visible_to_students','max_repeats','date_expired')
    list_filter = ['visible_to_students','max_repeats','verification_required']
    search_fields = ['name']
    inlines = [
        PrerequisiteInLine,
    ]

admin.site.register(Quest, QuestAdmin)
admin.site.register(Category)
admin.site.register(Prerequisite)
