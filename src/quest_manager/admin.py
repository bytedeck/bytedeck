from django.contrib import admin
from django.contrib import messages

from django_summernote.admin import SummernoteModelAdmin

# Register your models here.
from import_export import resources
from import_export.admin import ImportExportActionModelAdmin

from prerequisites.admin import PrereqInline

from .models import Quest, Category, QuestSubmission, CommonData


def publish_selected_quests(modeladmin, request, queryset):
    num_updates = queryset.update(visible_to_students=True, editor=None)

    msg_str = str(num_updates) + " quest(s) updated. Editors have been removed and the quest is now visible to students."
    messages.success(request, msg_str)


def archive_selected_quests(modeladmin, request, queryset):
    num_updates = queryset.update(archived=True, visible_to_students=False, editor=None);

    msg_str = str(num_updates) + " quest(s) archived. These quests will now only be visible through this admin menu."
    messages.success(request, msg_str)


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

    # default queryset doesn't return other semesters, or submissions for archived quests, or not visible to students
    def get_queryset(self, request):
        qs = QuestSubmission.objects.get_queryset(active_semester_only=False,
                                                  exclude_archived_quests=False,
                                                  exclude_quests_not_visible_to_students=False)
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        return qs


class QuestResource(resources.ModelResource):
    class Meta:
        model = Quest
        # exclude = ('id',)


class QuestAdmin(SummernoteModelAdmin, ImportExportActionModelAdmin):  # use SummenoteModelAdmin
    resource_class = QuestResource
    list_display = ('id', 'name', 'xp', 'archived', 'visible_to_students', 'max_repeats', 'date_expired',
                    'common_data', 'campaign', 'editor')
    list_filter = ['archived', 'visible_to_students', 'max_repeats', 'verification_required', 'editor']
    search_fields = ['name']
    inlines = [
        # TaggedItemInline
        PrereqInline,
    ]

    actions = [publish_selected_quests, archive_selected_quests]

    change_list_filter_template = "admin/filter_listing.html"

    # default queryset doesn't include archived quests
    def get_queryset(self, request):
        qs = Quest.objects.get_queryset(include_archived=True)
        return qs

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
