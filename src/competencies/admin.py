from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin

from .models import Competency, CompetencyAssessment, QuestCompetency


class CompetencyAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('name', 'category', 'source_id', 'active')
    list_filter = ('active', 'category')
    search_fields = ('name', 'description', 'source_id')


class QuestCompetencyAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('quest', 'competency', 'default_level')
    list_filter = ('default_level',)
    list_select_related = ('quest', 'competency')
    search_fields = ('quest__name', 'competency__name')


class CompetencyAssessmentAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('user', 'competency', 'level', 'assessed_by', 'source_object', 'timestamp')
    list_filter = ('level',)
    list_select_related = ('user', 'competency', 'assessed_by')
    search_fields = ('user__username', 'competency__name')
    date_hierarchy = 'timestamp'


admin.site.register(Competency, CompetencyAdmin)
admin.site.register(QuestCompetency, QuestCompetencyAdmin)
admin.site.register(CompetencyAssessment, CompetencyAssessmentAdmin)
