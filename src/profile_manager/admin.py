from django.contrib import admin
from portfolios.models import Artwork
from .models import Profile

# Register your models here.


class ProfileAdmin(admin.ModelAdmin):  # use SummenoteModelAdmin
    list_display = ('id', 'user_id', 'user', 'first_name', 'last_name', 'grad_year', )

    # readonly_fields = ('user_id', )
    #
    # def user_id(self, obj):
    #     return obj.user.pk

    #list_filter = ['is_completed', 'is_approved', 'semester']
    #search_fields = ['user']

    # # default queryset doesn't return other semesters, or submissions for archived quests, or not visible to students
    # def get_queryset(self, request):
    #     qs = QuestSubmission.objects.get_queryset(active_semester_only=False,
    #                                               exclude_archived_quests=False,
    #                                               exclude_quests_not_visible_to_students=False)
    #     ordering = self.get_ordering(request)
    #     if ordering:
    #         qs = qs.order_by(*ordering)
    #     return qs

admin.site.register(Profile, ProfileAdmin)
admin.site.register(Artwork)
