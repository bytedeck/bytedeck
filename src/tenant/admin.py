from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.admin import helpers, widgets
from django.core.exceptions import PermissionDenied
from django.contrib.sites.models import Site
from django.template.response import TemplateResponse
from django.db import connection, transaction
from django.utils.translation import ngettext
from django.contrib.admin.utils import unquote
from django.contrib.admin.exceptions import DisallowedModelAdminToField
from django.contrib.admin.options import TO_FIELD_VAR, IS_POPUP_VAR
from django.utils.translation import gettext as _
from django.utils.html import format_html
from django.utils.formats import date_format
from django.urls import reverse

from allauth.socialaccount.models import SocialApp
from allauth.account.models import EmailAddress
from allauth.account.utils import user_email
from django_tenants.utils import get_public_schema_name, tenant_context

from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget
from siteconfig.models import SiteConfig

from .models import Tenant, TenantDomain
from .forms import TenantBaseForm
from .utils import generate_schema_name
from .tasks import send_email_message


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
            'max_active_users', 'paid_until', 'trial_end_date',
            'stripe_customer_id', 'stripe_subscription_id', 'can_delete']

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


class ChangeDeckOwnerAdminForm(forms.Form):
    """Intermediate form for the "Change deck owner" action: pick the new owner
    from the selected deck's staff users (built per-deck by the action)."""
    # '_selected_action' (ACTION_CHECKBOX_NAME) is required for the admin intermediate form to submit
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)

    new_owner = forms.ChoiceField(
        label="New deck owner",
        help_text="Staff users on this deck. The chosen user is promoted to superuser; "
                  "the current owner's permissions are untouched.",
    )

    def __init__(self, *args, choices=(), **kwargs):
        """Attach the per-deck staff-user choices the action resolved.

        Args:
            choices (iterable): ``(username, label)`` pairs for the deck's
                staff users, excluding the current owner.
        """
        super().__init__(*args, **kwargs)
        self.fields['new_owner'].choices = choices


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
        'schema_name', 'owner_full_name_text',
        'owner_email_text', 'owner_email_verified_boolean',
        'last_staff_login', 'google_signon_enabled',
        'subscription_status_text', 'paid_until_text', 'trial_end_date_text',
        'max_active_users', 'active_user_count', 'total_user_count',
        'quest_count',
    )

    class Media:
        """Extra assets for the changelist: the Subscription column's badge
        stylesheet (.deck-status-*), since the admin doesn't load the app's
        bootstrap css."""
        css = {'all': ('css/admin_deck_status.css',)}
    list_filter = ('paid_until', 'trial_end_date', 'active_user_count', 'last_staff_login')
    search_fields = ['schema_name', 'owner_full_name_cached', 'owner_email_cached']

    form = TenantAdminForm
    inlines = (TenantDomainInline, )
    change_list_template = 'admin/tenant/tenant/change_list.html'
    delete_selected_confirmation_template = 'admin/tenant/tenant/delete_selected_confirmation.html'
    delete_confirmation_template = 'admin/tenant/tenant/delete_confirmation.html'

    actions = [
        'refresh_cached_fields', 'sync_from_stripe', 'verify_owner_email', 'change_deck_owner',
        'message_unverified', 'message_verified', 'enable_google_signin', 'disable_google_signin',
    ]

    @admin.action(description="Refresh deck stats for selected deck(s)")
    def refresh_cached_fields(self, request, queryset):
        """Refresh the selected decks' cached stats immediately, from the admin.

        The stats otherwise refresh nightly via the deck-status task; this action is
        the on-demand path (no SSH or management command needed). It runs
        synchronously so the numbers are fresh on the very next page load -- and it
        still works when celery is down, which is exactly when an admin might be
        investigating stale stats. The public schema row is skipped (not a deck).
        """
        skipped_public = queryset.filter(schema_name=get_public_schema_name()).exists()
        refreshed = 0
        for tenant in queryset.exclude(schema_name=get_public_schema_name()):
            with tenant_context(tenant):
                tenant.update_cached_fields()
            refreshed += 1
        self.message_user(request, f"Refreshed deck stats for {refreshed} deck(s).", messages.SUCCESS)
        if skipped_public:
            self.message_user(request, "Skipped the public schema (it isn't a deck).", messages.WARNING)

    @admin.action(description="Sync selected deck(s) from Stripe")
    def sync_from_stripe(self, request, queryset):
        """Re-fetch each selected Stripe-linked deck's subscription and re-sync it
        (epic #1729 PR 7, plan §5.3).

        This is both the missed-webhook recovery path and the linkage path for
        legacy manual subscribers (#2043): paste a stripe_subscription_id into the
        deck, save, then run this action. Decks without a stripe_subscription_id
        are skipped. Uses the same single write path as the webhook handlers
        (Tenant.sync_from_stripe_subscription).
        """
        import stripe as stripe_lib

        from django.conf import settings

        from tenant.billing import _sync_deck_from_subscription_id

        if not settings.STRIPE_SECRET_KEY:
            self.message_user(request, "Stripe isn't configured on this server (STRIPE_SECRET_KEY unset).", messages.ERROR)
            return
        synced, skipped, failed = 0, 0, 0
        for tenant in queryset:
            if not tenant.stripe_subscription_id:
                skipped += 1
                continue
            try:
                summary = _sync_deck_from_subscription_id(tenant, tenant.stripe_subscription_id)
            except stripe_lib.StripeError as e:
                failed += 1
                self.message_user(request, f"{tenant.schema_name}: Stripe error -- {e}", messages.ERROR)
                continue
            synced += 1
            self.message_user(request, f"{tenant.schema_name}: {summary}", messages.SUCCESS)
        if skipped:
            # the admin framework never dispatches an action with an empty selection,
            # so skipped/synced/failed always accounts for every selected row
            self.message_user(
                request,
                f"Skipped {skipped} deck(s) with no stripe_subscription_id (link them first, or use checkout).",
                messages.WARNING,
            )

    @admin.action(description="Verify owner email for selected deck(s)")
    def verify_owner_email(self, request, queryset):
        """Normalize each selected deck owner's allauth EmailAddress to
        verified+primary: the state deck creation produces (legacy decks predate
        that flow, so their owners often have no EmailAddress row at all). Uses
        the same write path as the ``backfill_owner_emails`` management command
        (tenant.utils.normalize_owner_email) and reports each deck's outcome as
        its own message; decks that need a human (no owner email, or the address
        is verified by a different account) are flagged rather than guessed at.
        """
        from library.utils import get_library_schema_name

        from .utils import normalize_owner_email

        for tenant in queryset.exclude(schema_name__in=[get_public_schema_name(), get_library_schema_name()]):
            try:
                # atomic() so a broken schema can't poison the connection for the rest
                with transaction.atomic(), tenant_context(tenant):
                    status, owner_name, email, notes = normalize_owner_email(tenant, apply_changes=True)
            except Exception as e:
                self.message_user(request, f"{tenant.schema_name}: ERROR {type(e).__name__}: {e}", messages.ERROR)
                continue
            summary = {
                'fixed': f"verified the owner's email ({owner_name} <{email}>)",
                'ok': f"owner email already verified ({owner_name} <{email}>)",
                'no-email': f"owner '{owner_name}' has NO email set: add one in the deck's Site Config first",
                'skipped': f"'{email}' is already verified by another account on the deck: needs a human",
            }[status]
            level = {'fixed': messages.SUCCESS, 'ok': messages.INFO}.get(status, messages.WARNING)
            note_suffix = f" ({notes})" if notes else ''
            self.message_user(request, f"{tenant.schema_name}: {summary}{note_suffix}", level)

    @admin.action(description="Change deck owner for the selected deck")
    def change_deck_owner(self, request, queryset):
        """Hand a deck to a new owner from the admin (legacy decks whose owner is
        the wrong account). Works on exactly ONE selected deck: an intermediate
        page lists that deck's staff users (minus the current owner) to pick
        from, then the switch runs through the same write path as the
        ``change_deck_owner`` management command (tenant.utils.switch_deck_owner):
        the new owner is promoted to superuser, the previous owner's permissions
        are untouched, and the deck's cached owner fields refresh immediately.
        """
        from library.utils import get_library_schema_name

        from .utils import switch_deck_owner

        queryset = queryset.exclude(schema_name__in=[get_public_schema_name(), get_library_schema_name()])
        if queryset.count() != 1:
            self.message_user(request, "Select exactly ONE deck to change its owner.", messages.ERROR)
            return None
        tenant = queryset.first()
        with tenant_context(tenant):
            current_owner = SiteConfig.get().deck_owner
            # the field is NOT NULL, but older admin code guards ownerless decks
            # (message_selected), so match that caution instead of 500ing on .pk
            if current_owner is None:
                self.message_user(
                    request,
                    f"{tenant.schema_name}: this deck has no owner set in its SiteConfig; fix it there first.",
                    messages.ERROR,
                )
                return None
            staff = User.objects.filter(is_staff=True).exclude(pk=current_owner.pk).order_by('username')
            choices = [
                (user.username, f"{user.get_full_name() or user.username} ({user.username})")
                for user in staff
            ]
        if not choices:
            self.message_user(
                request,
                f"{tenant.schema_name}: no other staff users on the deck to hand it to.",
                messages.WARNING,
            )
            return None

        if request.POST.get("post"):  # if admin pressed 'Change owner' on the intermediate page
            form = ChangeDeckOwnerAdminForm(data=request.POST, choices=choices)
            if form.is_valid():
                try:
                    old_username, new_username = switch_deck_owner(tenant, form.cleaned_data['new_owner'])
                except ValueError as e:  # pragma: no cover -- the form's choice validation already
                    # rejects unknown/non-staff users; this only guards the race where the user's
                    # account changes between the picker render and the confirm POST
                    self.message_user(request, f"{tenant.schema_name}: {e}", messages.ERROR)
                    return None
                self.message_user(
                    request,
                    f"{tenant.schema_name}: owner changed from '{old_username}' to '{new_username}' "
                    "(promoted to superuser). Now run \"Verify owner email\" on the deck to normalize "
                    "the new owner's email verification.",
                    messages.SUCCESS,
                )
                return None
        else:
            # '_selected_action' (ACTION_CHECKBOX_NAME) is required for the admin intermediate form to submit
            form = ChangeDeckOwnerAdminForm(initial={helpers.ACTION_CHECKBOX_NAME: [tenant.pk]}, choices=choices)

        adminform = helpers.AdminForm(form, [(None, {"fields": form.base_fields})], {})
        media = self.media + adminform.media
        request.current_app = self.admin_site.name
        return TemplateResponse(
            request,
            "admin/tenant/tenant/change_deck_owner.html",
            context={
                **self.admin_site.each_context(request),
                "title": f"Change the owner of deck '{tenant.schema_name}'",
                "adminform": adminform,
                "subtitle": None,
                "tenant": tenant,
                "current_owner": current_owner,
                "queryset": queryset,
                # building proper breadcrumb in admin
                "opts": self.model._meta,
                "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
                "media": media,
            },
        )

    @admin.display(description="owner full name")
    def owner_full_name_text(self, obj):
        return obj.owner_full_name_cached
    owner_full_name_text.admin_order_field = "owner_full_name_cached"

    @admin.display(description="owner email")
    def owner_email_text(self, obj):
        return obj.owner_email_cached
    owner_email_text.admin_order_field = "owner_email_cached"

    @admin.display(description="email verified", boolean=True)
    def owner_email_verified_boolean(self, obj):
        """
        Returns `True` (green), if at least one verified email address was found, otherwise `False`.
        """
        if obj.schema_name == get_public_schema_name():
            return  # skip public schema

        with tenant_context(obj):
            owner = SiteConfig.get().deck_owner
            # get the email address, but only primary and verified
            for primary_email_address in EmailAddress.objects.filter(user=owner, primary=True, verified=True):
                # make sure it's primary email for real
                if primary_email_address.email == user_email(owner):
                    return True
        return False

    @admin.display(description="subscription")
    def subscription_status_text(self, obj):
        """The deck's lifecycle status as a colored badge: the same status (and
        the same word) the deck owner sees on their subscription details page,
        both rendered from the shared ``Tenant.subscription_status`` precedence
        chain so the two can never disagree.

        Args:
            obj (Tenant): The changelist row's tenant.

        Returns:
            SafeString | None: The rendered ``<span>`` badge for a deck row, or
            None (an empty cell) for the public schema row, which isn't a deck.
        """
        if obj.schema_name == get_public_schema_name():
            return None
        return format_html(
            '<span class="deck-status deck-status-{}">{}</span>',
            obj.subscription_status,
            obj.subscription_status_label,
        )

    @admin.display(description="paid until", ordering="paid_until")
    def paid_until_text(self, obj):
        """Returns htmlized value of `paid_until` field"""
        if not obj.paid_until:
            return None
        return format_html(
            "<span data-date=\"{}\">{}</span>",
            obj.paid_until,
            date_format(obj.paid_until, use_l10n=True),
        )

    @admin.display(description="trial end date", ordering="trial_end_date")
    def trial_end_date_text(self, obj):
        """Returns htmlized value of `trial_end_date` field"""
        if not obj.trial_end_date:
            return None
        return format_html(
            "<span data-date=\"{}\">{}</span>",
            obj.trial_end_date,
            date_format(obj.trial_end_date, use_l10n=True),
        )

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

    def changelist_view(self, request, extra_context=None):
        """Attach a data-freshness notice to the deck list.

        The cached deck stats (current-student counts, owner info, quest counts) refresh via the
        nightly deck-status task, not on page load, so tell the admin how old the
        numbers they're looking at are.

        GET only: an action POST runs through this view too and then redirects (or
        re-renders), so a notice queued during the POST would survive into the next
        render and show as a duplicate beside the one the follow-up GET queues
        (production find after running the refresh action).
        """
        from django.db.models import Max
        from django.utils.timesince import timesince

        if request.method != 'GET':
            return super().changelist_view(request, extra_context)

        latest = self.model.objects.aggregate(latest=Max('cached_fields_updated_on'))['latest']
        if latest:
            messages.info(
                request,
                f"Deck stats (current-student counts, owner info, quest counts) were last refreshed {timesince(latest)} ago. "
                "They refresh nightly; to refresh now, select decks below and run the \"Refresh deck stats\" action."
            )
        else:
            messages.info(
                request,
                "Deck stats (current-student counts, owner info, quest counts) have not been refreshed yet. "
                "They refresh nightly; to refresh now, select decks below and run the \"Refresh deck stats\" action."
            )
        return super().changelist_view(request, extra_context)

    def has_delete_permission(self, request, obj=None):
        """Deletion is gated on the deck being abandoned (#2044 retirement policy).

        Per object, the Django delete permission must hold AND the deck must be
        deletable (suspended for over a year, counted from its first suspended
        notice -- ``Tenant.is_deletable``); this both hides the change form's
        Delete button and 403s the delete view for protected decks. With no
        object (module/changelist level) the default applies, so the model
        itself stays visible to authorized admins.
        """
        allowed = super().has_delete_permission(request, obj)
        if obj is None:
            return allowed
        return allowed and obj.is_deletable

    def delete_model(self, request, obj):
        """Delete the deck AND drop its Postgres schema (#2044 retirement policy).

        Re-checks the abandonment guard even though the delete view already
        enforces has_delete_permission -- schema drops are unrecoverable, so any
        future code path that reaches here must fail closed too.

        For reference: https://django-tenants.readthedocs.io/en/stable/use.html#deleting-a-tenant
        (auto_drop_schema stays False model-wide; only this admin flow force-drops.)
        """
        if not obj.is_deletable:
            raise PermissionDenied(
                "Only decks that have been suspended for over a year (counted from "
                "their first suspension notice) can be deleted."
            )
        obj.delete(force_drop=True)  # delete the row AND drop the schema

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

    @admin.action(description="Send an email message to *all* owners for the selected tenant(s)")
    def message_unverified(modeladmin, request, queryset):
        """Send an email message to *all* owners for selected tenant(s)."""
        return modeladmin.message_selected(request, queryset, verified=False)

    @admin.action(description="Send an email message to *verified* only owners for the selected tenant(s)")
    def message_verified(modeladmin, request, queryset):
        """Send an email message to *verified* only owners for selected tenant(s)."""
        return modeladmin.message_selected(request, queryset, verified=True)

    def message_selected(modeladmin, request, queryset, verified=True):
        """
        Send an email message to either *all* or *verified* only owners for selected tenant(s).

        This action first displays an intermediate page which shows compose message form and
        a list of all recipients.

        Next, it send email message to all selected users and redirects back to the change list.
        """
        # get a list of selected tenant(s), excluding public schema
        objects = modeladmin.model.objects.filter(
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

                email = ""
                for primary_email_address in EmailAddress.objects.filter(user=owner):
                    # get the email address, but only primary and verified
                    if verified and not (primary_email_address.verified and primary_email_address.primary):
                        continue
                    # make sure it's primary email for real
                    if primary_email_address.email == user_email(owner):
                        email = owner.email

                if len(email):  # skip, if email address is empty
                    recipient_list.append(f"{tenant.name} - {full_name_or_username} <{email}>")

        # Create a message informing the user that the recipients were not found
        # and return a redirect to the admin index page.
        if not len(recipient_list):
            modeladmin.message_user(request, "No recipients found.", messages.WARNING)
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
                modeladmin.message_user(request, "%s users emailed successfully!" % len(recipient_list), messages.SUCCESS)

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
        media = modeladmin.media + adminform.media

        request.current_app = modeladmin.admin_site.name

        # we need to create a template of intermediate page with form
        return TemplateResponse(
            request,
            "admin/tenant/tenant/message_selected_compose.html",
            context={
                **modeladmin.admin_site.each_context(request),
                "title": "Write your message here",
                "adminform": adminform,
                "subtitle": None,
                "recipient_list": recipient_list,
                "queryset": objects,
                # building proper breadcrumb in admin
                "opts": modeladmin.model._meta,
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
