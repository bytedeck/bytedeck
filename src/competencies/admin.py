from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin

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


class CompetencyAssessmentAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
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


class CompetencyOverrideAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
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
