from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin

from .models import Competency, CompetencyAssessment, QuestCompetency


class CompetencyAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    """ Admin for the deck's competency library. """
    list_display = ('name', 'category', 'source_id', 'active')
    list_filter = ('active', 'category')
    search_fields = ('name', 'description', 'source_id')


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


admin.site.register(Competency, CompetencyAdmin)
admin.site.register(QuestCompetency, QuestCompetencyAdmin)
admin.site.register(CompetencyAssessment, CompetencyAssessmentAdmin)
