from allauth.socialaccount.admin import SocialAccountAdmin, SocialAppAdmin

from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin
from django.contrib.sites.models import Site

from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from allauth.account.models import EmailAddress

from django_summernote.models import Attachment

from tenant.admin import PublicSchemaOnlyAdminAccessMixin


class SiteCustomAdmin(PublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = ('domain', 'name')
    search_fields = ('domain', 'name')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.unregister(Site)
admin.site.register(Site, SiteCustomAdmin)


class GroupCustomAdmin(PublicSchemaOnlyAdminAccessMixin, GroupAdmin):
    pass


admin.site.unregister(Group)
admin.site.register(Group, GroupCustomAdmin)


class SocialAppCustomAdmin(PublicSchemaOnlyAdminAccessMixin, SocialAppAdmin):
    pass


admin.site.unregister(SocialApp)
admin.site.register(SocialApp, SocialAppCustomAdmin)


class SocialAccountCustomAdmin(PublicSchemaOnlyAdminAccessMixin, SocialAccountAdmin):
    pass


admin.site.unregister(SocialAccount)
admin.site.register(SocialAccount, SocialAccountCustomAdmin)


# Remove a few more models from admin for now to simplify
admin.site.unregister(Attachment)
admin.site.unregister(SocialToken)
admin.site.unregister(EmailAddress)
