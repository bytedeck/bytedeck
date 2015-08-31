from django import forms
from django.contrib import admin
from django.contrib.contenttypes.admin  import GenericTabularInline
from django.contrib.contenttypes.models import ContentType

from django_summernote.admin import SummernoteModelAdmin

# Register your models here.
from prerequisites.admin import PrereqInline

from .models import Quest, Category, TaggedItem, QuestSubmission

class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id','user', 'quest')

# class TaggedItemInline(GenericTabularInline):
#     model = TaggedItem

class QuestAdmin(SummernoteModelAdmin): #use SummenoteModelAdmin
    list_display = ('name', 'xp','visible_to_students','max_repeats','date_expired')
    list_filter = ['visible_to_students','max_repeats','verification_required']
    search_fields = ['name']
    inlines = [
        # TaggedItemInline
        PrereqInline,
    ]

    change_list_filter_template = "admin/filter_listing.html"

    # fieldsets = [
    #     ('Available', {'fields': ['date_available', 'time_available']}),
    # ]

admin.site.register(Quest, QuestAdmin)
admin.site.register(Category)
admin.site.register(QuestSubmission)
# admin.site.register(Prereq)
# admin.site.register(Feedback, FeedbackAdmin)
# admin.site.register(TaggedItem)
