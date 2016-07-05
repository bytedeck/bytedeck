from django.contrib import admin
from django.contrib.contenttypes.admin  import GenericTabularInline

# Register your models here.
from .models import Semester, ExcludedDate, DateType, Block, CourseStudent, Course, Rank

class ExcludedDateInline(admin.TabularInline):
    model = ExcludedDate

class SemesterAdmin(admin.ModelAdmin):
    list_display = ('__str__','number','first_day','last_day','active', 'closed')
    inlines = [
        ExcludedDateInline,
    ]

class RankAdmin(admin.ModelAdmin):
    list_display = ('name','xp')


admin.site.register(CourseStudent)
admin.site.register(Semester, SemesterAdmin)
admin.site.register(Block)
admin.site.register(Course)
admin.site.register(DateType)
admin.site.register(Rank, RankAdmin)
