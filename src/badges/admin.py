from uuid import UUID
from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.contenttypes.models import ContentType

from import_export import resources
from import_export.admin import ImportExportActionModelAdmin
from import_export.fields import Field
from import_export.formats.base_formats import CSV

from prerequisites.models import Prereq
from prerequisites.admin import PrereqInline
from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from quest_manager.models import Quest

from .models import Badge, BadgeType, BadgeSeries, BadgeAssertion, BadgeRarity


class BadgeRarityAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('name', 'percentile', 'color', 'fa_icon')


class BadgeAssertionAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('badge', 'user', 'ordinal', 'timestamp')


class BadgeTypeAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('name', 'sort_order', 'fa_icon')


class BadgeResource(NonPublicSchemaOnlyAdminAccessMixin, resources.ModelResource):
    prereq_import_ids = Field(column_name='prereq_import_ids')

    badge_type_name = Field()
    badge_type_sort = Field()
    badge_type_icon = Field()

    class Meta:
        model = Badge
        import_id_fields = ('import_id',)

    def dehydrate_prereq_import_ids(self, quest):
        # save basic single/simple prerequisites, if there are any (no OR).
        # save as an & seperated list of import_ids (UUIDs)
        prereq_import_ids = ''
        for p in quest.prereqs():
            if p.prereq_content_type == ContentType.objects.get_for_model(Quest):
                prereq_import_ids += '&' + str(p.get_prereq().import_id)
            elif p.prereq_content_type == ContentType.objects.get_for_model(Badge):
                prereq_import_ids += '&' + str(p.get_prereq().import_id)
        return prereq_import_ids

    def dehydrate_badge_type_name(self, badge):
        """For processing "badge_type_name" field on export

        Using the name instead of id.
        We cannot guarantee exportee's ids are the same as import's ids
        Use badge_type.name instead as it is unique.
        """
        # dehydrate runs twice per row during import.
        # (despite import_export docs saying nothing about it running in import)
        # first run every variable is "None" and the only
        # accessible thing that doesnt produce an error is "badge.id"
        if not badge.id:
            return None
        return str(badge.badge_type)

    def dehydrate_badge_type_sort(self, badge):
        """For processing "badge_type_sort" field on export"""
        # dehydrate runs twice per row during import.
        # (despite import_export docs saying nothing about it running in import)
        # first run every variable is "None" and the only
        # accessible thing that doesnt produce an error is "badge.id"
        if not badge.id:
            return None
        return badge.badge_type.sort_order

    def dehydrate_badge_type_icon(self, badge):
        """For processing "badge_type_icon" field on export"""
        # dehydrate runs twice per row during import.
        # (despite import_export docs saying nothing about it running in import)
        # first run every variable is "None" and the only
        # accessible thing that doesnt produce an error is "badge.id"
        if not badge.id:
            return None
        return badge.badge_type.fa_icon

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

    def generate_badge_type(self, row):
        """modifies the row "badge_type" to the correct BadgeType.id defined by
         + badge_type_name
         + badge_type_sort
         + badge_type_icon
        If badge type doesn't exist, it creates it.
        If staff cancels import anything created here will be rolled back automatically.
        """
        bt_name = row['badge_type_name']
        bt_sort = row['badge_type_sort']
        bt_icon = row['badge_type_icon']

        if bt_name:
            defaults = {'fa_icon': bt_icon}

            # if bt_sort is None badge creation will throw an error
            if bt_sort:
                defaults['sort_order'] = bt_sort

            badge_type, _ = BadgeType.objects.get_or_create(
                name=bt_name,
                defaults=defaults,
            )

            row['badge_type'] = badge_type.id

    def before_import_row(self, row, **kwargs):
        """https://django-import-export.readthedocs.io/en/3.3.9/api_resources.html#import_export.resources.Resource.before_import_row"""
        # can create badge type here as it seems like the new badgetype will be saved only be saved
        # after admin has accepted the import changes
        self.generate_badge_type(row)

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        """https://django-import-export.readthedocs.io/en/3.3.9/api_resources.html#import_export.resources.Resource.after_import"""
        for data_dict in dataset.dict:
            import_id = data_dict['import_id']
            parent_badge = Badge.objects.get(import_id=import_id)
            self.generate_simple_prereqs(parent_badge, data_dict)


class BadgeAdmin(NonPublicSchemaOnlyAdminAccessMixin, ImportExportActionModelAdmin):
    resource_class = BadgeResource
    list_display = ('name', 'xp', 'active')
    inlines = [
        PrereqInline,
    ]

    def get_import_formats(self):
        """file formats for importing"""
        return [CSV]

    def get_export_formats(self):
        """file formats for exporting"""
        return [CSV]


class BadgeSeriesAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


admin.site.register(Badge, BadgeAdmin)
admin.site.register(BadgeType, BadgeTypeAdmin)
admin.site.register(BadgeSeries, BadgeSeriesAdmin)
admin.site.register(BadgeRarity, BadgeRarityAdmin)
admin.site.register(BadgeAssertion, BadgeAssertionAdmin)
