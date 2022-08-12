from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from .models import Semester, ExcludedDate, DateType, Block, CourseStudent, Course, Rank, Grade, MarkRange


class ExcludedDateInline(admin.TabularInline):
    model = ExcludedDate


class SemesterAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('__str__', 'first_day', 'last_day', 'closed')
    inlines = [
        ExcludedDateInline,
    ]


class MarkRangeAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'minimum_mark', 'active', 'color_light', 'color_dark', 'days')


class RankAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('name', 'xp')


class CourseStudentAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):  # use SummenoteModelAdmin
    list_display = ('__str__', 'user', 'semester', 'course', 'final_grade', 'active')
    # actions = [convert_selected_grade_to_fk]

    list_filter = ['course', ]
    search_fields = ['user__username']


class BlockAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


class GradeAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


class CourseAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


class DataTypeAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    pass


admin.site.register(Rank, RankAdmin)
admin.site.register(Block, BlockAdmin)
admin.site.register(Grade, GradeAdmin)
admin.site.register(Course, CourseAdmin)
admin.site.register(DateType, DataTypeAdmin)
admin.site.register(Semester, SemesterAdmin)
admin.site.register(MarkRange, MarkRangeAdmin)
admin.site.register(CourseStudent, CourseStudentAdmin)
