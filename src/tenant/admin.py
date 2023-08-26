import operator
from functools import reduce

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.admin import helpers, widgets
from django.core.exceptions import PermissionDenied
from django.contrib.sites.models import Site
from django.template.response import TemplateResponse
from django.db import connection, transaction
from django.db.models import Q, F
from django.utils.translation import ngettext
from django.utils.text import smart_split, unescape_string_literal
from django.contrib.admin.utils import unquote
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.contrib.admin.options import TO_FIELD_VAR, IS_POPUP_VAR
from django.utils.translation import gettext as _
from django.urls import reverse

from allauth.socialaccount.models import SocialApp
from allauth.account.models import EmailAddress
from allauth.account.utils import user_email
from django_tenants.utils import tenant_context, schema_context, get_public_schema_name

from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget
from siteconfig.models import SiteConfig
from tenant.models import Tenant, TenantDomain
from tenant.forms import TenantBaseForm
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


class TenantAdminForm(TenantBaseForm):

    class Meta(TenantBaseForm.Meta):
        fields = TenantBaseForm.Meta.fields + [
            'owner_full_name', 'owner_email', 'max_active_users', 'max_quests', 'paid_until', 'trial_end_date']

    def clean_name(self):
        name = super().clean_name()
        if self.instance.schema_name and self.instance.schema_name != generate_schema_name(name):
            # if the schema already exists, then can't change the name
            raise forms.ValidationError("The name cannot be changed after the tenant is created.")
        return name


class SendEmailAdminForm(forms.Form):
    # '_selected_action' (ACTION_CHECKBOX_NAME) is required for the admin intermediate form to submit
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)

    subject = forms.CharField(
        widget=widgets.AdminTextInputWidget(attrs={"placeholder": "Subject"}))
    message = forms.CharField(widget=ByteDeckSummernoteSafeWidget)


class DeleteConfirmationForm(forms.Form):
    confirmation = forms.CharField(required=True, widget=widgets.AdminTextInputWidget)

    # Say friend and enter (Doors of Durin)
    keyword = None

    def __init__(self, *args, **kwargs):
        self.target_object = kwargs.pop("target_object")
        super().__init__(*args, **kwargs)

        # generate keyword as confirmation code / phrase
        keyword = str(self.target_object.name)
        with tenant_context(self.target_object):
            owner = SiteConfig.get().deck_owner or None
            keyword = "/".join([owner.username if owner else "bytedeck", keyword])
        self.keyword = keyword

    def clean(self):
        cleaned_data = super().clean()

        confirmation = cleaned_data.get("confirmation", "")
        if confirmation and confirmation != self.keyword:
            self.add_error("confirmation", _("The confirmation does not match the keyword"))

        return cleaned_data


class TenantAdmin(PublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
    list_display = (
        'schema_name', 'owner_full_name_text', 'owner_full_name_deprecated',
        'owner_email_text', 'owner_email_deprecated',
        'last_staff_login', 'google_signon_enabled',
        'paid_until', 'trial_end_date',
        'max_active_users', 'active_user_count', 'total_user_count',
        'max_quests', 'quest_count',
    )
    list_filter = ('paid_until', 'trial_end_date', 'active_user_count', 'last_staff_login')
    # DEPRECATED: these fields ("owner_full_name" and "owner_email") will be removed in a future update
    search_fields = ['schema_name', 'owner_full_name', 'owner_email']

    form = TenantAdminForm
    inlines = (TenantDomainInline, )
    change_list_template = 'admin/tenant/tenant/change_list.html'
    delete_selected_confirmation_template = 'admin/tenant/tenant/delete_selected_confirmation.html'
    delete_confirmation_template = 'admin/tenant/tenant/delete_confirmation.html'

    actions = ['message_selected', 'enable_google_signin', 'disable_google_signin']

    @admin.display(description="owner full name")
    def owner_full_name_text(self, obj):
        """
        Returns full name (or username) from SiteConfig().deck_owner object.
        """
        if obj.schema_name == get_public_schema_name():
            return  # skip public schema

        full_name_or_username = None
        with tenant_context(obj):
            owner = SiteConfig.get().deck_owner
            # get the full name of the user, or if none is supplied will return the username
            full_name_or_username = owner.get_full_name() or owner.username
        return full_name_or_username

    @admin.display(description="owner full name (DEPRECATED)")
    def owner_full_name_deprecated(self, obj):
        """This field will be removed in a future update"""
        return obj.owner_full_name
    owner_full_name_deprecated.admin_order_field = "owner_full_name"

    @admin.display(description="owner email")
    def owner_email_text(self, obj):
        """
        Returns email address (primary and verified) from SiteConfig().deck_owner object.
        """
        if obj.schema_name == get_public_schema_name():
            return  # skip public schema

        email = None
        with tenant_context(obj):
            owner = SiteConfig.get().deck_owner
            # get the email address, but only primary and verified
            for primary_email_address in EmailAddress.objects.filter(user=owner, primary=True, verified=True):
                # make sure it's primary email for real
                if primary_email_address.email == user_email(owner):
                    email = owner.email
        return email

    @admin.display(description="owner email (DEPRECATED)")
    def owner_email_deprecated(self, obj):
        """This field will be removed in a future update"""
        return obj.owner_email
    owner_email_deprecated.admin_order_field = "owner_email"

    def get_search_results(self, request, queryset, search_term):
        """
        The `get_search_results` method modifies the list of objects displayed into those
        that match the provided search term. It accepts the request, a queryset that applies
        the current filters, and the user-provided search term. It returns a tuple containing a
        queryset modified to implement the search, and a boolean indicating if the results
        may contain duplicates.

        This method was overridden to perform search on custom fields.
        """
        # The default implementation searches the fields named in ModelAdmin.search_fields.
        queryset, may_have_duplicates = super().get_search_results(request, queryset, search_term)

        # search_term is what you input in admin site
        if not search_term:
            return queryset, False

        # getting a list of all schemas, except the public schema name
        schemas = list(Tenant.objects.all().values_list("schema_name", flat=True))
        schemas.remove(get_public_schema_name())

        # perform search on custom fields: "owner_full_name", "owner_email"
        search_fields = ["deck_owner__first_name", "deck_owner__last_name", "deck_owner__username", "deck_owner__email"]

        # you need to take a copy of the list and iterate over it first,
        # or the iteration will fail with what may be unexpected results.
        for schema in schemas[:]:
            with schema_context(schema):
                orm_lookups = ["%s__icontains" % str(search_field) for search_field in search_fields]

                for bit in smart_split(search_term):  # ["spam", "egg"]
                    if bit.startswith(('"', "'")) and bit[0] == bit[-1]:
                        bit = unescape_string_literal(bit)
                    or_queries = []
                    for orm_lookup in orm_lookups:
                        # get the email address, but only primary and verified
                        if "deck_owner__email" in orm_lookup:
                            or_queries.append(Q(**{
                                "deck_owner__emailaddress__verified": True,
                                "deck_owner__emailaddress__primary": True,
                                # make sure it's primary email for real
                                "deck_owner__emailaddress__email__exact": F("deck_owner__email"),
                                orm_lookup: bit,
                            }))
                        else:
                            or_queries.append(Q(**{orm_lookup: bit}))
                    qs = SiteConfig.objects.filter(reduce(operator.or_, or_queries))

                # if nothing was found within schema context
                if not qs.exists():
                    schemas.remove(schema)

        # return original queryset, OR any new results we found by searching within schema context
        if len(schemas):
            queryset |= self.model.objects.filter(schema_name__in=schemas)

        # we must establish if the queryset changes implemented by our search method
        # may introduce duplicates into the results, and return True in the second
        # element of the return value.
        return queryset, True

    def get_actions(self, request):
        """
        The method ``ModelAdmin.get_actions`` returns the list of registered actions.

        By overriding this method, to remove `delete_selected`. We can remove it form the dropdown.
        """
        actions = super().get_actions(request)
        # Removing "delete_selected" action in admin
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Update cached fields
        for tenant in qs:
            if tenant.name != get_public_schema_name():
                with tenant_context(tenant):
                    tenant.update_cached_fields()
        return qs

    def delete_model(self, request, obj):
        # for reference: https://django-tenants.readthedocs.io/en/stable/use.html#deleting-a-tenant
        obj.delete(force_drop=False)  # delete model, but *DO NOT* drop schema

    def _delete_view(self, request, object_id, extra_context):
        """Custom `_delete_view` method.

        This is the original method from ``ModelAdmin`` class that adds
        extra confirmation (must type keyword / phrase) instead of original
        simple two-step deletion.

        # See: https://github.com/django/django/blob/main/django/contrib/admin/options.py#L2125

        """
        app_label = self.opts.app_label

        to_field = request.POST.get(TO_FIELD_VAR, request.GET.get(TO_FIELD_VAR))
        if to_field and not self.to_field_allowed(request, to_field):
            raise DisallowedModelAdminToField(
                "The field %s cannot be referenced." % to_field
            )

        obj = self.get_object(request, unquote(object_id), to_field)

        if not self.has_delete_permission(request, obj):
            raise PermissionDenied

        if obj is None:
            return self._get_obj_does_not_exist_redirect(request, self.opts, object_id)

        # Populate deleted_objects, a data structure of all related objects that
        # will also be deleted.
        (
            deleted_objects,
            model_count,
            perms_needed,
            protected,
        ) = self.get_deleted_objects([obj], request)

        if request.POST.get("post") and not protected:  # The user has confirmed the deletion.
            if perms_needed:
                raise PermissionDenied
            form = DeleteConfirmationForm(data=request.POST, target_object=obj)
            if form.is_valid():
                obj_display = str(obj)
                attr = str(to_field) if to_field else self.opts.pk.attname
                obj_id = obj.serializable_value(attr)
                self.log_deletion(request, obj, obj_display)
                self.delete_model(request, obj)

                return self.response_delete(request, obj_display, obj_id)
        else:
            # create form and pass the data with target object before triggering 'post' action.
            form = DeleteConfirmationForm(target_object=obj)

        object_name = str(self.opts.verbose_name)

        if perms_needed or protected:
            title = _("Cannot delete %(name)s") % {"name": object_name}
        else:
            title = _("Are you sure?")

        # AdminForm is a class within the `django.contrib.admin.helpers` module of the Django project.
        #
        # AdminForm is not usually used directly by developers, but can be used by libraries that want to
        # extend the forms within the Django Admin.
        adminform = helpers.AdminForm(form, [(None, {"fields": form.base_fields})], {})
        media = self.media + adminform.media

        context = {
            **self.admin_site.each_context(request),
            "title": title,
            "subtitle": None,
            "adminform": adminform,
            "object_name": object_name,
            "object": obj,
            "deleted_objects": deleted_objects,
            "model_count": dict(model_count).items(),
            "perms_lacking": perms_needed,
            "protected": protected,
            # building proper breadcrumb in admin
            "opts": self.opts,
            "app_label": app_label,
            "media": media,
            "preserved_filters": self.get_preserved_filters(request),
            "is_popup": IS_POPUP_VAR in request.POST or IS_POPUP_VAR in request.GET,
            "to_field": to_field,
            **(extra_context or {}),
        }

        return self.render_delete_form(request, context)

    @admin.action(description="Send an email message to all owners for the selected tenant(s)")
    def message_selected(self, request, queryset):
        """
        Send an email message to all owners for selected tenant(s).

        This action first displays an intermediate page which shows compose message form and
        a list of all recipients.

        Next, it send email message to all selected users and redirects back to the change list.
        """
        # get a list of selected tenant(s), excluding public schema
        objects = self.model.objects.filter(
            pk__in=[str(x) for x in request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)]
        ).exclude(schema_name=get_public_schema_name())

        # get a list of all owners (recipients) for selected tenant(s)
        recipient_list = []
        for tenant in objects:
            with tenant_context(tenant):
                owner = SiteConfig.get().deck_owner or None
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
