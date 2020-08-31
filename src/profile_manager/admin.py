from django.contrib import admin
from django.contrib import messages
from django.contrib.auth.models import User

from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin

from .models import Profile, create_profile


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


def migrate_names_to_user_model(modeladmin, request, queryset):
    for profile in queryset:
        if hasattr(profile, 'first_name') and profile.first_name:
            profile.user.first_name = profile.first_name
        if hasattr(profile, 'last_name') and profile.last_name:
            profile.user.last_name = profile.last_name
        
        profile.user.save()

    messages.success(request, "Complete")


@admin.register(Profile)
class ProfileAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):  # use SummenoteModelAdmin
    list_display = ('id', 'get_username', 'get_full_name', 'preferred_name', 'xp_cached', 'grad_year', 'is_TA', 'banned_from_comments')

    actions = [create_missing_profiles, migrate_names_to_user_model]

    list_filter = ['is_TA', 'grad_year', 'banned_from_comments', 'get_announcements_by_email', 'get_notifications_by_email']
    search_fields = ['user__username', 'user__first_name', 'user__first_name', 'preferred_name']

    def get_username(self, obj):
        return obj.user.get_username()
    get_username.short_description = "Username"

    def get_full_name(self, obj):
        return obj.user.get_full_name()
    get_full_name.short_description = "Full name"
