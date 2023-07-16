from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.admin import helpers, widgets
from django.contrib.sites.models import Site
from django.template.response import TemplateResponse
from django.db import connection, transaction
from django.utils.translation import ngettext
from django.urls import reverse

from allauth.socialaccount.models import SocialApp
from allauth.account.models import EmailAddress
from allauth.account.utils import user_email
from django_tenants.utils import get_public_schema_name
from django_tenants.utils import tenant_context

from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget
from tenant.models import Tenant, TenantDomain
from tenant.utils import generate_schema_name
from tenant.tasks import send_email_message

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


class SendEmailAdminForm(forms.Form):
    # '_selected_action' (ACTION_CHECKBOX_NAME) is required for the admin intermediate form to submit
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)

    subject = forms.CharField(
        widget=widgets.AdminTextInputWidget(attrs={"placeholder": "Subject"}))
    message = forms.CharField(widget=ByteDeckSummernoteSafeWidget)


class TenantAdmin(PublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = (
        'schema_name', 'owner_full_name', 'owner_email', 'last_staff_login',
        'google_signon_enabled',
        'paid_until', 'trial_end_date',
        'max_active_users', 'active_user_count', 'total_user_count',
        'max_quests', 'quest_count',
    )
    list_filter = ('paid_until', 'trial_end_date', 'active_user_count', 'last_staff_login')
    search_fields = ['schema_name', 'owner_full_name', 'owner_email']

    form = TenantAdminForm
    inlines = (TenantDomainInline, )
    change_list_template = 'admin/tenant/tenant/change_list.html'

    actions = ['message_selected', 'enable_google_signin', 'disable_google_signin']

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

    @admin.action(description="Send an email message to all owners for the selected tenant(s)")
    def message_selected(self, request, queryset):
        """
        Send an email message to all owners for selected tenant(s).

        This action first displays an intermediate page which shows compose message form and
        a list of all recipients.

        Next, it send email message to all selected users and redirects back to the change list.
        """
        from siteconfig.models import SiteConfig

        def get_owner_or_none():
            """Returns owner (User) object or None"""
            return SiteConfig.get().deck_owner or None

        # get a list of selected tenant(s), excluding public schema
        objects = self.model.objects.filter(
            pk__in=[str(x) for x in request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)]
        ).exclude(schema_name=get_public_schema_name())

        # get a list of all owners (recipients) for selected tenant(s)
        recipient_list = []
        for tenant in objects:
            with tenant_context(tenant):
                owner = get_owner_or_none()
                if owner is None:  # where is the owner?
                    continue
                # get the full name of the user, or if none is supplied will return the username
                full_name_or_username = owner.get_full_name() or owner.username

                # get the email address, but only primary and verified
                email = ""
                for primary_email_address in EmailAddress.objects.filter(user=owner, primary=True, verified=True):
                    # make sure it's primary email for real
                    if primary_email_address.email == user_email(owner):
                        email = owner.email

                if len(email):  # skip, if email address is empty
                    recipient_list.append(f"{tenant.name} - {full_name_or_username} <{email}>")

        # Create a message informing the user that the recipients were not found
        # and return a redirect to the admin index page.
        if not len(recipient_list):
            self.message_user(request, "No recipients found.", messages.WARNING)
            # return None to display the change list page again.
            return None

        # Removing duplicate elements from the list.
        #
        # Using *set() is the fastest and smallest method to achieve it.
        # It first removes the duplicates and returns unpacked set using * operator
        # which has to be converted to list.
        recipient_list = [*set(recipient_list)]

        if request.POST.get("post"):  # if admin pressed 'post' on intermediate page
            form = SendEmailAdminForm(data=request.POST)
            if form.is_valid():
                cleaned_data = form.cleaned_data

                # run background task that will send email messages
                send_email_message.apply_async(
                    # subject, message and recipient_list (emails)
                    args=[cleaned_data["subject"], cleaned_data["message"], recipient_list],
                    queue="default",
                )

                # show alert that everything is cool
                self.message_user(request, "%s users emailed successfully!" % len(recipient_list), messages.SUCCESS)

                # return None to display the change list page again.
                return None
        else:
            # create form and pass the data which objects were selected before triggering 'post' action.
            # '_selected_action' (ACTION_CHECKBOX_NAME) is required for the admin intermediate form to submit
            form = SendEmailAdminForm(initial={helpers.ACTION_CHECKBOX_NAME: objects.values_list("id", flat=True)})

        # AdminForm is a class within the `django.contrib.admin.helpers` module of the Django project.
        #
        # AdminForm is not usually used directly by developers, but can be used by libraries that want to
        # extend the forms within the Django Admin.
        adminform = helpers.AdminForm(form, [(None, {"fields": form.base_fields})], {})
        media = self.media + adminform.media

        request.current_app = self.admin_site.name

        # we need to create a template of intermediate page with form
        return TemplateResponse(
            request,
            "admin/tenant/tenant/message_selected_compose.html",
            context={
                **self.admin_site.each_context(request),
                "title": "Write your message here",
                "adminform": adminform,
                "subtitle": None,
                "recipient_list": recipient_list,
                "queryset": objects,
                # building proper breadcrumb in admin
                "opts": self.model._meta,
                "DEFAULT_FROM_EMAIL": settings.DEFAULT_FROM_EMAIL,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
                "media": media,
            },
        )

    @admin.action(description="Enable google signin for tenant(s)")
    def enable_google_signin(self, request, queryset):
        from siteconfig.models import SiteConfig

        try:
            SocialApp.objects.get(provider='google')
        except SocialApp.DoesNotExist:
            self.message_user(request, "You must create a SocialApp record with 'google' as the provider", messages.ERROR)
            return

        queryset = queryset.exclude(schema_name=get_public_schema_name())
        enabled_tenant_domains = []
        for tenant in queryset:
            with tenant_context(tenant):
                config = SiteConfig.get()
                with transaction.atomic():
                    config._propagate_google_provider()
                    config.enable_google_signin = True
                    config.save()

                tenant_domain = tenant.get_primary_domain()
                uri = request.build_absolute_uri().replace(Site.objects.get_current().domain, tenant_domain.domain)

                # Create a URL {tenant}.{domain}/accounts/google/login/callback/
                uri = uri.replace(request.path, reverse("google_callback"))

                enabled_tenant_domains.append(uri)

        enabled_count = queryset.count()

        tenant_domains = ", ".join(enabled_tenant_domains)
        self.message_user(request, ngettext(
            "%d tenant google signin was enabled successfully. Please ensure that the tenant domain %s is added in the Authorized Redirect URIs for this OAuth 2.0 Client ID on Google Cloud",  # noqa
            "%d tenant google signins were enabled successfully. Please ensure that the tenant domains %s are added in the Authorized Redirect URIs for this OAuth 2.0 Client ID on Google Cloud",  # noqa
            enabled_count,
        ) % (enabled_count, tenant_domains), messages.SUCCESS)

    @admin.action(description="Disable google signin for tenant(s)")
    def disable_google_signin(self, request, queryset):
        from siteconfig.models import SiteConfig

        queryset = queryset.exclude(schema_name=get_public_schema_name())
        for tenant in queryset:
            with tenant_context(tenant):
                config = SiteConfig.get()
                config.enable_google_signin = False
                config.save()

        disabled_count = queryset.count()
        self.message_user(request, ngettext(
            "%d tenant google signin was disabled successfully",
            "%d tenant google signins were disabled successfully",
            disabled_count,
        ) % disabled_count, messages.SUCCESS)


admin.site.register(Tenant, TenantAdmin)
