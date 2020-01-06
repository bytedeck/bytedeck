from django.contrib import admin
from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django_summernote.admin import SummernoteModelAdmin
# Register your models here.
from import_export import resources
from import_export.admin import ImportExportActionModelAdmin
from import_export.fields import Field

from prerequisites.admin import PrereqInline
from prerequisites.models import Prereq
from .models import Quest, Category, QuestSubmission, CommonData
from .signals import tidy_html


def publish_selected_quests(modeladmin, request, queryset):
    num_updates = queryset.update(visible_to_students=True, editor=None)

    msg_str = "{} quest(s) updated. Editors have been removed and the quest is now visible to students.".format(str(num_updates)) # noqa
    messages.success(request, msg_str)


def archive_selected_quests(modeladmin, request, queryset):
    num_updates = queryset.update(archived=True, visible_to_students=False, editor=None)

    msg_str = str(num_updates) + " quest(s) archived. These quests will now only be visible through this admin menu."
    messages.success(request, msg_str)


def prettify_code_selected_quests(modeladmin, request, queryset):
    for quest in queryset:
        quest.instructions = tidy_html(quest.instructions)

    Quest.objects.bulk_update(queryset, ['instructions'])
    msg_str = "Quest instructions html prettified for the {} selected quest(s).".format(len(queryset))
    messages.success(request, msg_str)


def fix_whitespace_bug(modeladmin, request, queryset):
    for quest in queryset:
        quest.instructions = tidy_html(quest.instructions, fix_runaway_newlines=True)

    Quest.objects.bulk_update(queryset, ['instructions'])
    msg_str = "Quest instructions html prettified for the {} selected quest(s).".format(len(queryset))
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
    search_fields = ['user__username']

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
    prereq_quest_import_id = Field(column_name='prereq_quest_import_id')
    campaign_title = Field()
    campaign_icon = Field()

    class Meta:
        model = Quest
        import_id_fields = ('import_id',)
        exclude = ('id', 'editor', 'specific_teacher_to_notify', 'campaign', 'common_data')

    def dehydrate_prereq_quest_import_id(self, quest):
        # save basic single/simple prerequisite quest, if there is one.
        prereqs = Prereq.objects.all_parent(quest)
        for p in prereqs:
            if p.prereq_content_type == ContentType.objects.get_for_model(Quest):
                return p.get_prereq().import_id

    def dehydrate_campaign_title(self, quest):
        if quest.campaign:
            return quest.campaign.title
        else:
            return None

    def dehydrate_campaign_icon(self, quest):
        if quest.campaign:
            return quest.campaign.icon
        else:
            return None

    def generate_simple_prereqs(self, parent_quest, data_dict):
        # check that the prereq quest exists as an import-linked quest via import_id

        prereq_quest_import_id = data_dict["prereq_quest_import_id"]

        if prereq_quest_import_id:
            try:
                prereq_quest = Quest.objects.get(import_id=prereq_quest_import_id)
            except ObjectDoesNotExist:
                return False

            existing_prereqs_groups = Prereq.objects.all_parent(parent_quest)

            # generate list of objects for already existing primary prereq
            existing_primary_prereqs = [p.get_prereq() for p in existing_prereqs_groups]

            # check if the imported prereq already exists
            if prereq_quest in existing_primary_prereqs:
                return False
            else:
                # Create a new prereq to this quest
                Prereq.add_simple_prereq(parent_quest, prereq_quest)
        return True

    def generate_campaign(self, quest, data_dict):
        campaign_title = data_dict["campaign_title"]
        campaign_icon = data_dict["campaign_icon"]

        campaign, created = Category.objects.get_or_create(
            title=campaign_title,
            defaults={'icon': campaign_icon},
        )

        quest.campaign = campaign
        quest.save()

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        for data_dict in dataset.dict:
            import_id = data_dict["import_id"]
            parent_quest = Quest.objects.get(import_id=import_id)

            self.generate_simple_prereqs(parent_quest, data_dict)

            self.generate_campaign(parent_quest, data_dict)


class QuestAdmin(SummernoteModelAdmin, ImportExportActionModelAdmin):  # use SummenoteModelAdmin
    resource_class = QuestResource
    list_display = ('id', 'name', 'xp', 'archived', 'visible_to_students', 'max_repeats', 'date_expired',
                    'common_data', 'campaign', 'editor')
    list_filter = ['archived', 'visible_to_students', 'max_repeats', 'verification_required', 'editor']
    search_fields = ['name', 'instructions', 'submission_details', 'short_description']
    inlines = [
        # TaggedItemInline
        PrereqInline,
    ]

    actions = [publish_selected_quests, archive_selected_quests, prettify_code_selected_quests, fix_whitespace_bug]

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
