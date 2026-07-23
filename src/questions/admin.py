from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin

from .models import Question, QuestionSubmission


class QuestionAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    """Admin for a quest's questions; tenant schemas only."""
    list_display = ('__str__', 'quest', 'type', 'required', 'datetime_created')
    list_filter = ('type', 'required')


class QuestionSubmissionAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    """Admin for students' question answers; tenant schemas only."""
    list_display = ('__str__', 'question', 'quest_submission', 'comment', 'datetime_created')


admin.site.register(Question, QuestionAdmin)
admin.site.register(QuestionSubmission, QuestionSubmissionAdmin)
