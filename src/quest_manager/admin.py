from django.contrib import admin

from django_summernote.admin import SummernoteModelAdmin

# Register your models here.
from prerequisites.admin import PrereqInline

from .models import Quest, Category, QuestSubmission, CommonData


class FeedbackAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'quest')


# class TaggedItemInline(GenericTabularInline):
#     model = TaggedItem

class CommonDataAdmin(SummernoteModelAdmin):
    pass


class QuestSubmissionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'quest', 'is_completed', 'is_approved', 'semester')
    list_filter = ['is_completed', 'is_approved', 'semester']
    search_fields = ['user']

    # default queryset doesn't return other semesters
    def get_queryset(self, request):
        qs = QuestSubmission.objects.get_queryset(active_semester_only=False)
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs


class QuestAdmin(SummernoteModelAdmin):  # use SummenoteModelAdmin
    list_display = ('id', 'name', 'xp', 'visible_to_students', 'max_repeats', 'date_expired', 'common_data', 'campaign',)
    list_filter = ['visible_to_students', 'max_repeats', 'verification_required']
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
admin.site.register(CommonData, CommonDataAdmin)
admin.site.register(QuestSubmission, QuestSubmissionAdmin)
# admin.site.register(Prereq)
# admin.site.register(Feedback, FeedbackAdmin)
# admin.site.register(TaggedItem)
