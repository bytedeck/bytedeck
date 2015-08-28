from django.contrib import admin
from django.contrib.contenttypes.admin  import GenericTabularInline

# Register your models here.
from .models import Semester, ExcludedDate, DateType, Block, CourseStudent, Course, Rank

class ExcludedDateInline(admin.TabularInline):
    model = ExcludedDate


# class BlockInline(admin.TabularInline):
#     model = Block

class SemesterAdmin(admin.ModelAdmin):
    inlines = [
        ExcludedDateInline,
    ]
# class FeedbackAdmin(admin.ModelAdmin):
#     list_display = ('id','user', 'quest')
#
# # class TaggedItemInline(GenericTabularInline):
# #     model = TaggedItem
#
# class PrerequisiteInline(admin.TabularInline):
#     model = Prerequisite
#     fk_name = "parent_quest"
#     extra = 1
#
# class
#
# class Semester(admin.ModelAdmin): #use SummenoteModelAdmin
#     search_fields = ['name']
#     inlines = [
#         PrerequisiteInline,
#         # TaggedItemInline
#     ]
# admin.site.register(Quest, QuestAdmin)
admin.site.register(CourseStudent)
admin.site.register(Semester, SemesterAdmin)
admin.site.register(Block)
admin.site.register(Course)
admin.site.register(DateType)
admin.site.register(Rank)
