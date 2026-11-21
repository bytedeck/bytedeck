from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin

from .assessments import queue_conditions_update
from .models import Competency, CompetencyAssessment, CompetencyOverride, QuestCompetency


class CompetencyAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    """ Admin for the deck's competency library. """
    list_display = ('name', 'course', 'category', 'source_id', 'active')
    list_filter = ('active', 'course', 'category')
    search_fields = ('name', 'course', 'description', 'source_id')


class QuestCompetencyAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    """ Admin for the Quest-to-Competency links. """
    list_display = ('quest', 'competency', 'default_level')
    list_filter = ('default_level',)
    list_select_related = ('quest', 'competency')
    search_fields = ('quest__name', 'competency__name')


class RecalculateConditionsAdminMixin:
    """ For the admins of records a student's current level is worked out from (assessments and
    overrides): adding, changing or deleting one can change the level, so the student's available
    quests are recalculated, as when a teacher records a level through the app
    (competencies.assessments.queue_conditions_update). """

    def save_model(self, request, obj, form, change):
        """ Saves the record, then recalculates for its student, and for the student it belonged to
        before when the change moved it to someone else. """
        super().save_model(request, obj, form, change)
        user_ids = {obj.user_id}
        if change and 'user' in form.changed_data:
            user_ids.add(form.initial['user'])
        queue_conditions_update(*user_ids)

    def delete_model(self, request, obj):
        """ Deletes the record, then recalculates for its student. """
        user_id = obj.user_id
        super().delete_model(request, obj)
        queue_conditions_update(user_id)

    def delete_queryset(self, request, queryset):
        """ Deletes the selected records (the changelist's bulk delete), then recalculates once for each
        of their students, read before the records are gone. """
        user_ids = set(queryset.values_list('user_id', flat=True))
        super().delete_queryset(request, queryset)
        queue_conditions_update(*user_ids)


class CompetencyAssessmentAdmin(RecalculateConditionsAdminMixin, NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    """ Admin for assessment evidence records.

    The changelist shows the raw source_content_type and source_object_id halves of the
    generic source FK: resolving source_object itself would cost a query per row (a
    generic FK can't be covered by list_select_related), and the id is enough to
    identify the source at a glance.
    """
    list_display = ('user', 'competency', 'level', 'assessed_by', 'source_content_type', 'source_object_id', 'timestamp')
    list_filter = ('level',)
    list_select_related = ('user', 'competency', 'assessed_by', 'source_content_type')
    search_fields = ('user__username', 'competency__name')
    date_hierarchy = 'timestamp'


class CompetencyOverrideAdmin(RecalculateConditionsAdminMixin, NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    """ Admin for teachers' overrides of students' levels: every record, including those since replaced
    or cleared (a record with no level), so the history of overrides can be audited. """
    list_display = ('user', 'competency', 'level', 'set_by', 'timestamp', 'note')
    list_filter = ('level',)
    list_select_related = ('user', 'competency', 'set_by')
    search_fields = ('user__username', 'competency__name', 'note')
    date_hierarchy = 'timestamp'


admin.site.register(Competency, CompetencyAdmin)
admin.site.register(QuestCompetency, QuestCompetencyAdmin)
admin.site.register(CompetencyAssessment, CompetencyAssessmentAdmin)
admin.site.register(CompetencyOverride, CompetencyOverrideAdmin)
