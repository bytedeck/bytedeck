from uuid import UUID
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.contenttypes.models import ContentType

from import_export import resources
from import_export.fields import Field
from import_export.admin import ImportExportActionModelAdmin, ExportActionMixin

from prerequisites.models import Prereq
from prerequisites.admin import PrereqInline
from badges.models import Badge
from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from bytedeck_summernote.admin import ByteDeckSummernoteSafeModelAdmin, ByteDeckSummernoteAdvancedModelAdmin

from .signals import tidy_html
from .models import Quest, Category, QuestSubmission, CommonData


def publish_selected_quests(modeladmin, request, queryset):
    num_updates = queryset.update(visible_to_students=True, editor=None)

    msg_str = "{} quest(s) updated. Editors have been removed and the quest is now visible to students.".format(
        str(num_updates))  # noqa
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

class CommonDataAdmin(NonPublicSchemaOnlyAdminAccessMixin, ByteDeckSummernoteSafeModelAdmin):
    pass


class QuestSubmissionAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
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
    prereq_import_ids = Field(column_name='prereq_import_ids')
    campaign_title = Field()
    campaign_icon = Field()

    class Meta:
        model = Quest
        import_id_fields = ('import_id',)
        exclude = ('id', 'editor', 'specific_teacher_to_notify', 'campaign', 'common_data')

    def dehydrate_prereq_import_ids(self, quest):
        # save basic single/simple prerequisites, if there are any (no OR).
        # save as an & seperated list of import_ids (UUIDs)
        prereq_import_ids = ""
        for p in quest.prereqs():
            if p.prereq_content_type == ContentType.objects.get_for_model(Quest):
                prereq_import_ids += "&" + str(p.get_prereq().import_id)
            elif p.prereq_content_type == ContentType.objects.get_for_model(Badge):
                prereq_import_ids += "&" + str(p.get_prereq().import_id)
        return prereq_import_ids

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

    def generate_simple_prereqs(self, parent_object, data_dict):
        # check that the prereq quest exists as an import-linked quest via import_id

        prereq_import_ids = data_dict["prereq_import_ids"]
        prereq_import_ids = prereq_import_ids.split('&')
        prereq_object = None

        for import_id in prereq_import_ids:
            if import_id:  # can be blank sometimes
                try:
                    prereq_object = Quest.objects.get(import_id=UUID(import_id))
                except ObjectDoesNotExist:
                    try:
                        prereq_object = Badge.objects.get(import_id=UUID(import_id))
                    except ObjectDoesNotExist:
                        pass

            if prereq_object:

                existing_prereqs_groups = parent_object.prereqs()
                # generate list of objects for already existing primary prereq
                existing_primary_prereqs = [p.get_prereq() for p in existing_prereqs_groups]

                # check if the imported prereq already exists
                if prereq_object in existing_primary_prereqs:
                    pass
                else:
                    # Create a new prereq to this quest
                    Prereq.add_simple_prereq(parent_object, prereq_object)

    def generate_campaign(self, quest, data_dict):
        campaign_title = data_dict["campaign_title"]
        campaign_icon = data_dict["campaign_icon"]

        # Might not have a campaign.
        if campaign_title:
            campaign, created = Category.objects.get_or_create(
                title=campaign_title,
                defaults={'icon': campaign_icon},
            )

            quest.campaign = campaign
            quest.save()

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        if not dry_run:
            for data_dict in dataset.dict:
                import_id = data_dict["import_id"]
                parent_quest = Quest.objects.get(import_id=import_id)

                self.generate_simple_prereqs(parent_quest, data_dict)

                self.generate_campaign(parent_quest, data_dict)


class QuestAdmin(NonPublicSchemaOnlyAdminAccessMixin, ByteDeckSummernoteAdvancedModelAdmin, ImportExportActionModelAdmin):  # use SummenoteModelAdmin
    resource_class = QuestResource
    list_display = ('id', 'name', 'xp', 'archived', 'visible_to_students', 'blocking', 'sort_order', 'max_repeats', 'date_expired',
                    'editor', 'specific_teacher_to_notify', 'common_data', 'campaign')
    list_filter = ['archived', 'visible_to_students', 'max_repeats', 'verification_required', 'editor', 
                   'specific_teacher_to_notify', 'common_data', 'campaign']
    search_fields = ['name', 'instructions', 'submission_details', 'short_description', 'campaign__title']
    inlines = [
        # TaggedItemInline
        PrereqInline,
    ]

    actions = ExportActionMixin.actions + [publish_selected_quests, archive_selected_quests,
                                           prettify_code_selected_quests, fix_whitespace_bug]  # noqa

    change_list_filter_template = "admin/filter_listing.html"

    # default queryset doesn't include archived quests
    def get_queryset(self, request):
        qs = Quest.objects.get_queryset(include_archived=True)
        return qs

    # fieldsets = [
    #     ('Available', {'fields': ['date_available', 'time_available']}),
    # ]


class CategoryAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


admin.site.register(Quest, QuestAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(CommonData, CommonDataAdmin)
admin.site.register(QuestSubmission, QuestSubmissionAdmin)
# admin.site.register(Prereq)
# admin.site.register(Feedback, FeedbackAdmin)
# admin.site.register(TaggedItem)
