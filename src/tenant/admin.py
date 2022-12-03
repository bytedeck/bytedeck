from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.db import connection

from django_tenants.utils import get_public_schema_name
from django_tenants.utils import tenant_context

# from quest_manager.models import Quest

from tenant.models import Tenant, TenantDomain
from tenant.utils import generate_schema_name

User = get_user_model()


class PublicSchemaOnlyAdminAccessMixin:
    def has_view_or_change_permission(self, request, obj=None):
        return connection.schema_name == get_public_schema_name()

    def has_add_permission(self, request):
        return connection.schema_name == get_public_schema_name()

    def has_module_permission(self, request):
        return connection.schema_name == get_public_schema_name()


class NonPublicSchemaOnlyAdminAccessMixin:
    def has_view_or_change_permission(self, request, obj=None):
        return connection.schema_name != get_public_schema_name()

    def has_add_permission(self, request):
        return connection.schema_name != get_public_schema_name()

    def has_module_permission(self, request):
        return connection.schema_name != get_public_schema_name()


class TenantDomainInline(admin.TabularInline):
    model = TenantDomain
    readonly_fields = ('domain', 'is_primary')
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class TenantAdminForm(forms.ModelForm):

    class Meta:
        model = Tenant
        fields = ['name', 'owner_full_name', 'owner_email', 'max_active_users', 'max_quests', 'paid_until', 'trial_end_date']

    def clean_name(self):
        name = self.cleaned_data["name"]
        # has already validated the model field at this point
        if name == "public":
            raise forms.ValidationError("The public tenant is restricted and cannot be edited")
        elif self.instance.schema_name and self.instance.schema_name != generate_schema_name(name):
            # if the schema already exists, then can't change the name
            raise forms.ValidationError("The name cannot be changed after the tenant is created")
        else:
            # TODO
            # finally, check that there isn't a schema on the db that doesn't have a tenant object
            # and thus doesn't care about name validation/uniqueness.
            pass

        return name


class TenantAdmin(PublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = (
        'schema_name', 'owner_full_name', 'owner_email', 'last_staff_login',
        'paid_until', 'trial_end_date',
        'max_active_users', 'active_user_count', 'total_user_count',
        'max_quests', 'quest_count',
    )
    list_filter = ('paid_until', 'trial_end_date', 'active_user_count', 'last_staff_login')
    search_fields = ['schema_name', 'owner_full_name', 'owner_email']

    form = TenantAdminForm
    inlines = (TenantDomainInline, )
    change_list_template = 'admin/tenant/tenant/change_list.html'

    def delete_model(self, request, obj):
        messages.error(request, 'Tenants must be deleted manually from `manage.py shell`;  \
            and the schema deleted from the db via psql: `DROP SCHEMA schema_name CASCADE;`. \
            ignore the success message =D')

        # don't delete
        return

    def has_delete_permission(self, request, obj=None):
        # Disable delete button and admin action
        return False

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Update cached fields
        for tenant in qs:
            if tenant.name != get_public_schema_name():
                with tenant_context(tenant):
                    tenant.update_cached_fields()
        return qs


admin.site.register(Tenant, TenantAdmin)
