from uuid import UUID
from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.contenttypes.models import ContentType

from import_export import resources
from import_export.fields import Field
from import_export.formats.base_formats import CSV
from import_export.admin import ImportExportActionModelAdmin

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
    msg_str = f"Quest instructions html prettified for the {len(queryset)} selected quest(s)."
    messages.success(request, msg_str)


def fix_whitespace_bug(modeladmin, request, queryset):
    for quest in queryset:
        quest.instructions = tidy_html(quest.instructions, fix_runaway_newlines=True)

    Quest.objects.bulk_update(queryset, ['instructions'])
    msg_str = f"Quest instructions html prettified for the {len(queryset)} selected quest(s)."
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
    autocomplete_fields = ("draft_comment",)

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
    """
    A resource class for importing and exporting Quests using django-import-export.

    This class enables Quests to be serialized and deserialized across schemas,
    such as importing from the library into tenant schemas. It supports linking
    related data like campaigns (Categories) using a UUID-based `import_id`.

    generate_campaign_from_import_data: Automatically finds or creates a Campaign
    for the imported Quest based on import_id or title, ensuring proper cross-schema linking.

    Intended for use in multi-tenant environments where Quests need to be
    shared, cloned, or updated from a central library source.

    Related behavior like prerequisites and tags are handled by associated mixins
    on the Quest model, not directly by this class.
    """
    prereq_import_ids = Field(column_name='prereq_import_ids')
    campaign_title = Field()
    campaign_icon = Field()
    campaign_short_description = Field()
    campaign_import_id = Field()

    class Meta:
        model = Quest
        import_id_fields = ('import_id',)
        exclude = ('id', 'editor', 'specific_teacher_to_notify', 'campaign', 'common_data')

    def dehydrate_prereq_import_ids(self, quest):
        """
        Returns a string of prerequisite import IDs for the given quest.

        This method is used during data export to include a list of prerequisite
        quest or badge import IDs (UUIDs), separated by '&', in the exported dataset.
        Only simple prerequisites (no OR logic) are included. If there are no prerequisites,
        returns an empty string.

        Args:
            quest (Quest): The quest instance being exported.

        Returns:
            str: A string of prerequisite import IDs separated by '&', or an empty string.
        """
        # save basic single/simple prerequisites, if there are any (no OR).
        # save as an & seperated list of import_ids (UUIDs)
        prereq_import_ids = ''
        for p in quest.prereqs():
            if p.prereq_content_type in [ContentType.objects.get_for_model(Quest), ContentType.objects.get_for_model(Badge)]:
                prereq_import_ids += '&' + str(p.get_prereq().import_id)
        return prereq_import_ids

    def dehydrate_campaign_title(self, quest):
        """
        Returns the title of the campaign associated with the given quest.

        This method is used during data export to include the campaign's title
        in the exported dataset. If the quest does not have an associated campaign,
        returns None.

        Args:
            quest (Quest): The quest instance being exported.

        Returns:
            str or None: The title of the campaign, or None if not available.
        """
        if quest.campaign:
            return quest.campaign.title
        return None

    def dehydrate_campaign_icon(self, quest):
        """
        Returns the icon of the campaign associated with the given quest.

        This method is used during data export to include the campaign's icon
        in the exported dataset. If the quest does not have an associated campaign,
        returns None.

        Args:
            quest (Quest): The quest instance being exported.

        Returns:
            str or None: The icon of the campaign, or None if not available.
        """
        if quest.campaign:
            return quest.campaign.icon
        else:
            return None

    def dehydrate_campaign_short_description(self, quest):
        """
        Returns the short description of the campaign associated with the given quest.

        This method is used during data export to include the campaign's short description
        in the exported dataset. If the quest does not have an associated campaign,
        returns None.
        """
        if quest.campaign:
            return quest.campaign.short_description
        return None

    def dehydrate_campaign_import_id(self, quest):
        """
        Returns the import ID of the campaign associated with the given quest.

        This method is used during data export to include the campaign's import ID
        in the exported dataset. If the quest does not have an associated campaign,
        returns None.

        Args:
            quest (Quest): The quest instance being exported.

        Returns:
            UUID or None: The import ID of the campaign, or None if not available.
        """
        if quest.campaign and quest.campaign.import_id:
            return str(quest.campaign.import_id)
        return None

    def generate_simple_prereqs(self, parent_object, data_dict):
        # check that the prereq quest exists as an import-linked quest via import_id

        prereq_import_ids = data_dict['prereq_import_ids']
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
        """
        Assigns or creates a campaign (Category) for the given quest based on the provided data dictionary.

        Priority is given to matching an existing campaign via its import_id. If no match is found,
        the method attempts to find a campaign by its title. If neither exists, a new campaign is created
        using the provided title, icon, short description, and import_id.

        Args:
            quest (Quest): The quest instance to which the campaign will be assigned.
            data_dict (dict): A dictionary containing campaign data, including:
                - 'campaign_title': The title of the campaign.
                - 'campaign_icon': The icon of the campaign.
                - 'campaign_short_description': A short description of the campaign.
                - 'campaign_import_id': The import ID of the campaign (UUID).

        Side Effects:
            - The quest's `campaign` field is updated updated and saved.
            - A new Category Object may be created if no existing match is found.
        """
        campaign_title = data_dict.get('campaign_title')
        campaign_icon = data_dict.get('campaign_icon')
        campaign_short_description = data_dict.get('campaign_short_description')
        campaign_import_id = data_dict.get('campaign_import_id')

        campaign = None

        # Try to find import_id
        if campaign_import_id:
            try:
                campaign = Category.objects.get(import_id=UUID(campaign_import_id))
            except (Category.DoesNotExist, ValueError):
                pass

        # Fallback to title
        if not campaign and campaign_title:
            campaign = Category.objects.filter(title=campaign_title).first()

        if not campaign:
            # Create a new campaign if it doesn't exist
            campaign = Category.objects.create(
                title=campaign_title,
                icon=campaign_icon,
                short_description=campaign_short_description,
                import_id=UUID(campaign_import_id) if campaign_import_id else None
            )

        # Assign the campaign to the quest
        quest.campaign = campaign
        quest.save()

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        if not dry_run:
            for data_dict in dataset.dict:
                import_id = data_dict['import_id']
                parent_quest = Quest.objects.get(import_id=import_id)

                self.generate_simple_prereqs(parent_quest, data_dict)
                if (data_dict.get('campaign_title') or data_dict.get('campaign_import_id')):
                    # Only generate campaign if title or import_id is provided
                    # This prevents unnecessary campaign creation for quests without campaigns
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

    actions = [publish_selected_quests, archive_selected_quests, prettify_code_selected_quests, fix_whitespace_bug]

    change_list_filter_template = "admin/filter_listing.html"

    # default queryset doesn't include archived quests
    def get_queryset(self, request):
        qs = Quest.objects.get_queryset(include_archived=True)
        return qs

    # fieldsets = [
    #     ('Available', {'fields': ['date_available', 'time_available']}),
    # ]

    def get_import_formats(self):
        """ file formats for importing """
        return [CSV]

    def get_export_formats(self):
        """ file formats for exporting """
        return [CSV]


class CategoryAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


admin.site.register(Quest, QuestAdmin)
admin.site.register(Category, CategoryAdmin)
admin.site.register(CommonData, CommonDataAdmin)
admin.site.register(QuestSubmission, QuestSubmissionAdmin)
# admin.site.register(Prereq)
# admin.site.register(Feedback, FeedbackAdmin)
# admin.site.register(TaggedItem)
