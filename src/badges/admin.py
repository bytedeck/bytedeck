from uuid import UUID
from django.contrib import admin
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.contenttypes.models import ContentType

from import_export import resources
from import_export.admin import ImportExportActionModelAdmin
from import_export.fields import Field

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

    class Meta:
        model = Badge
        import_id_fields = ('import_id',)

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

    def after_import(self, dataset, result, using_transactions, dry_run, **kwargs):
        for data_dict in dataset.dict:
            import_id = data_dict["import_id"]
            parent_badge = Badge.objects.get(import_id=import_id)
            self.generate_simple_prereqs(parent_badge, data_dict)


class BadgeAdmin(NonPublicSchemaOnlyAdminAccessMixin, ImportExportActionModelAdmin):
    resource_class = BadgeResource
    list_display = ('name', 'xp', 'active')
    inlines = [
        PrereqInline,
    ]


class BadgeSeriesAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


admin.site.register(Badge, BadgeAdmin)
admin.site.register(BadgeType, BadgeTypeAdmin)
admin.site.register(BadgeSeries, BadgeSeriesAdmin)
admin.site.register(BadgeRarity, BadgeRarityAdmin)
admin.site.register(BadgeAssertion, BadgeAssertionAdmin)
