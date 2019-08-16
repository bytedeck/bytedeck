from django.contrib import admin
# from django.contrib.contenttypes.admin  import GenericTabularInline

# Register your models here.
from .models import Semester, ExcludedDate, DateType, Block, CourseStudent, Course, Rank, Grade, MarkRange


# def convert_selected_grade_to_fk(modeladmin, request, queryset):
#     for course_student in queryset:
#         current_grade_field = course_student.grade
#         grade_fk, created = Grade.objects.get_or_create(
#             name=str(current_grade_field),
#             value=current_grade_field,
#         )
#
#         if course_student.grade_fk is None:
#             course_student.grade_fk = grade_fk
#             course_student.save()


class ExcludedDateInline(admin.TabularInline):
    model = ExcludedDate


class SemesterAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'number', 'first_day', 'last_day', 'active', 'closed')
    inlines = [
        ExcludedDateInline,
    ]


class MarkRangeAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'minimum_mark', 'active', 'color_light', 'color_dark', 'days')


class RankAdmin(admin.ModelAdmin):
    list_display = ('name', 'xp')


class CourseStudentAdmin(admin.ModelAdmin):  # use SummenoteModelAdmin
    list_display = ('__str__', 'user', 'semester', 'course', 'grade_fk', 'final_grade', 'active')
    # actions = [convert_selected_grade_to_fk]

    list_filter = ['course', 'grade_fk', ]
    search_fields = ['user__username']


admin.site.register(CourseStudent, CourseStudentAdmin)
admin.site.register(Semester, SemesterAdmin)
admin.site.register(Block)
admin.site.register(Course)
admin.site.register(DateType)
admin.site.register(Grade)
admin.site.register(MarkRange, MarkRangeAdmin)
admin.site.register(Rank, RankAdmin)
