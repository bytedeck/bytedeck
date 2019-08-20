from django.contrib import admin
from django.contrib import messages

from portfolios.models import Artwork
from django.contrib.auth.models import User
from .models import Profile, create_profile

# Register your models here.


def create_missing_profiles(modeladmin, request, queryset):
    users = User.objects.all()
    new_profiles = []
    for user in users:
        if not hasattr(user, 'profile'):
            # print(user.username + ": No profile ********************************")
            create_profile(None, **{'instance': user, 'created': True})
            new_profiles.append(user.username)

    if new_profiles:
        msg_str = "New profiles created for: " + str(new_profiles)
        messages.success(request, msg_str)


class ProfileAdmin(admin.ModelAdmin):  # use SummenoteModelAdmin
    list_display = ('id', 'user_id', 'user', 'first_name', 'last_name', 'student_number', 'grad_year', 'is_TA',)

    actions = [create_missing_profiles]

    # readonly_fields = ('user_id', )
    #
    # def user_id(self, obj):
    #     return obj.user.pk

    list_filter = ['is_TA', 'grad_year', ]
    search_fields = ['first_name', 'last_name', 'user__username', 'student_number']

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
