
from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin
from django.contrib.sites.models import Site
from django.contrib.flatpages.models import FlatPage
from django.contrib.flatpages.admin import FlatPageAdmin

from allauth.socialaccount.models import SocialAccount, SocialToken, SocialApp
from allauth.account.models import EmailAddress

from django_summernote.admin import SummernoteModelAdmin
from django_summernote.models import Attachment

from tenant.admin import PublicSchemaOnlyAdminAccessMixin, NonPublicSchemaOnlyAdminAccessMixin


class FlatPageAdmin2(NonPublicSchemaOnlyAdminAccessMixin, FlatPageAdmin, SummernoteModelAdmin):
    list_display = ('url', 'title', 'registration_required',)


admin.site.unregister(FlatPage)
admin.site.register(FlatPage, FlatPageAdmin2)


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


# Remove a few more models from admin for now to simplify
admin.site.unregister(Attachment)
admin.site.unregister(SocialAccount)
admin.site.unregister(SocialToken)
admin.site.unregister(SocialApp)
admin.site.unregister(EmailAddress)
