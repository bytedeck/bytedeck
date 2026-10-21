from django.contrib import admin

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin
from .forms import class_days_changed
from .models import Semester, ExcludedDate, Block, CourseStudent, Course, Rank, Grade, MarkRange


class ExcludedDateInline(admin.TabularInline):
    model = ExcludedDate


class SemesterAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('__str__', 'first_day', 'last_day', 'status')
    inlines = [
        ExcludedDateInline,
    ]

    def save_related(self, request, form, formsets, change):
        """Save the semester's excluded dates, then have its students' cached marks worked out
        again when its class days changed, as the semester form does (#2899).

        Args:
            request (HttpRequest): the admin's request.
            form (ModelForm): the semester's form, already saved.
            formsets (list): the inline formsets, here its excluded dates.
            change (bool): whether an existing semester was edited.
        """
        super().save_related(request, form, formsets, change)
        if class_days_changed(form, formsets):
            form.instance.refresh_cached_marks_on_commit()


class MarkRangeAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('id', 'name', 'minimum_mark', 'active', 'color_headers', 'color_light', 'color_dark', 'days')


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
admin.site.register(Semester, SemesterAdmin)
admin.site.register(MarkRange, MarkRangeAdmin)
admin.site.register(CourseStudent, CourseStudentAdmin)
