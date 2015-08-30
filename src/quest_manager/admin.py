from django.contrib import admin
from django.contrib.contenttypes.admin  import GenericTabularInline
from django_summernote.admin import SummernoteModelAdmin

# Register your models here.
from .models import Quest, Category, Prerequisite, TaggedItem, QuestSubmission, Prereq

class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id','user', 'quest')

# class TaggedItemInline(GenericTabularInline):
#     model = TaggedItem

class PrerequisiteInline(admin.TabularInline):
    model = Prerequisite
    fk_name = "parent_quest"
    extra = 1

class PrereqInline(GenericTabularInline):
    model = Prereq
    fk_name = "parent_object"
    ct_field = "parent_content_type"
    ct_fk_field = "parent_object_id"


class QuestAdmin(SummernoteModelAdmin): #use SummenoteModelAdmin
    list_display = ('name', 'xp','visible_to_students','max_repeats','date_expired')
    list_filter = ['visible_to_students','max_repeats','verification_required']
    search_fields = ['name']
    inlines = [
        PrerequisiteInline,
        # TaggedItemInline
        PrereqInline,
    ]

    # fieldsets = [
    #     ('Available', {'fields': ['date_available', 'time_available']}),
    # ]

admin.site.register(Quest, QuestAdmin)
admin.site.register(Category)
admin.site.register(QuestSubmission)
# admin.site.register(Prereq)
# admin.site.register(Feedback, FeedbackAdmin)
# admin.site.register(TaggedItem)
