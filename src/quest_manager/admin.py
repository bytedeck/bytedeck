import ipdb
from django.contrib import admin
from django.contrib.contenttypes.admin  import GenericTabularInline
from django.contrib.contenttypes.models import ContentType


from django_summernote.admin import SummernoteModelAdmin

# Register your models here.
from prerequisites.models import Prereq
from .models import Quest, Category, TaggedItem, QuestSubmission

class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id','user', 'quest')

# class TaggedItemInline(GenericTabularInline):
#     model = TaggedItem

class PrereqInline(GenericTabularInline):
    model = Prereq
    ct_field = "parent_content_type"
    ct_fk_field = "parent_object_id"
    fk_name = "parent_object"

    extra = 1

    autocomplete_lookup_fields = {
        'generic': [
                        ['prereq_content_type', 'prereq_object_id'],
                        ['or_prereq_content_type','or_prereq_object_id'],
                    ]
    }

    # def queryset(self, request):
    #     ipdb.set_trace()  ######### Break Point ###########
    #
    #     qs = super(PrereqInline, self).queryset(request)
    #     qs = qs.filter(pk__gte = 5)
    #     return qs

    # # limit fields to only models with a "conditions_met" method
    # def __init__(self, *args, **kwargs):
    #
    #     super(PrereqInline, self).__init__(*args, **kwargs)
    #     self.fields['ct_field'].queryset = ContentType.objects.all()


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
