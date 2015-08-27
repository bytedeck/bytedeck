from django.contrib import admin
from django.contrib.contenttypes.admin  import GenericTabularInline

# Register your models here.
from .models import Semester, ExcludedDate, DateType, Block, CourseStudent, Course

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


# class Semester(models.Model):
#     SEMESTER_CHOICES = ((1,1),(2,2),)
#
#     number = models.PositiveIntegerField(choices=SEMESTER_CHOICES)
#     first_day = models.DateField(blank=True, null=True)
#     last_day = models.DateField(blank=True, null=True)
#
# class ExcludedDate(models.Model):
#     semester = models.ForeignKey(Semester)
#     date_type = models.ForeignKey(DateType)
#     date = models.DateField(unique=True)
#
# class DateType(models.Model):
#     date_type = models.CharField(max_length=50, unique=True)
#
# class Block(models.Model):
#     block = models.CharField(max_length=50, unique=True)
#
# class CourseStudent(model.Models):
#     user = models.ForeignKey(settings.AUTH_USER_MODEL)
#     semester = models.ForeignKey(Semester)
#     block = models.ForeignKey(Block)
#     course = models.ForeignKey(Course)
#     grade = models.PositiveIntegerField()
#     active = models.BooleanField(default=True)
#
# class Course(models.Model):
#     title = models.CharField(max_length=50, unique=True)
#     icon = models.ImageField(upload_to='icons/', null=True, blank=True)
#     active = models.BooleanField(default=True)
