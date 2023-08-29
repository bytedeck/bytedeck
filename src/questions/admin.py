from django.contrib import admin

from .models import Question, QuestionSubmission
# Register your models here.
admin.site.register(Question)
admin.site.register(QuestionSubmission)
