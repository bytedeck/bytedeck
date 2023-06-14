"""
Misc. tenant-specific admin actions.
"""

from django import forms
from django.contrib import messages
from django.contrib.admin import helpers, widgets
from django.contrib.admin.decorators import action
from django.contrib.admin.utils import model_ngettext
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.utils.translation import gettext as _

from coolname import generate
from django_tenants.utils import get_public_schema_name


class DeleteSelectedConfirmationForm(forms.Form):
    # '_selected_action' (ACTION_CHECKBOX_NAME) is required for the admin intermediate form to submit
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)

    confirmation = forms.CharField(required=True, widget=widgets.AdminTextInputWidget)
    # Say friend and enter (Doors of Durin)
    keyword = forms.CharField(widget=forms.HiddenInput)

    def clean(self):
        cleaned_data = super().clean()

        confirmation = cleaned_data.get("confirmation", "")
        keyword = cleaned_data.get("keyword", "")
        if confirmation and confirmation != keyword:
            self.add_error("confirmation", _("The confirmation does not match the keyword"))

        return cleaned_data


@action(
    permissions=["delete"],
    description="Delete selected %(verbose_name_plural)s",
)
def delete_selected(modeladmin, request, queryset):
    """
    Default action which deletes the selected objects.

    This action first displays a confirmation page which shows all the
    deletable objects, or, if the user has no permission one of the related
    childs (foreignkeys), a "permission denied" message.

    Next, it deletes all selected objects and redirects back to the change list.
    """
    opts = modeladmin.model._meta
    app_label = opts.app_label

    objects = modeladmin.model.objects.filter(
        pk__in=[str(x) for x in request.POST.getlist(helpers.ACTION_CHECKBOX_NAME)]).exclude(
            schema_name=get_public_schema_name())

    # Populate deletable_objects, a data structure of all related objects that
    # will also be deleted.
    (
        deletable_objects,
        model_count,
        perms_needed,
        protected,
    ) = modeladmin.get_deleted_objects(objects, request)

    # Do the deletion and return None to display the change list view again.
    if request.POST.get("post") and not protected:  # The user has confirmed the deletion.
        if perms_needed:
            raise PermissionDenied
        form = DeleteSelectedConfirmationForm(data=request.POST)
        if form.is_valid():
            n = len(queryset)
            if n:
                for obj in queryset:
                    obj_display = str(obj)
                    modeladmin.log_deletion(request, obj, obj_display)
                modeladmin.delete_queryset(request, queryset)
                # show alert that everything is cool
                modeladmin.message_user(
                    request,
                    "Successfully deleted %(count)d %(items)s."
                    % {"count": n, "items": model_ngettext(modeladmin.opts, n)},
                    messages.SUCCESS,
                )

            # return None to display the change list page again.
            return None
    else:
        # create form and pass the data which objects were selected before triggering 'post' action.
        # '_selected_action' (ACTION_CHECKBOX_NAME) is required for the admin intermediate form to submit
        form = DeleteSelectedConfirmationForm(
            initial={
                helpers.ACTION_CHECKBOX_NAME: objects.values_list("id", flat=True),
                # generate "sekret" keyword from two random words
                "keyword": "/".join(generate(2)),
            },
        )

    objects_name = model_ngettext(objects)

    if perms_needed or protected:
        title = _("Cannot delete %(name)s") % {"name": objects_name}
    else:
        title = _("Are you sure?")

    # AdminForm is a class within the `django.contrib.admin.helpers` module of the Django project.
    #
    # AdminForm is not usually used directly by developers, but can be used by libraries that want to
    # extend the forms within the Django Admin.
    adminform = helpers.AdminForm(form, [(None, {"fields": form.base_fields})], {})
    media = modeladmin.media + adminform.media

    context = {
        **modeladmin.admin_site.each_context(request),
        "title": title,
        "subtitle": None,
        "adminform": adminform,
        "objects_name": str(objects_name),
        "deletable_objects": [deletable_objects],
        "model_count": dict(model_count).items(),
        "queryset": objects,
        "perms_lacking": perms_needed,
        "protected": protected,
        # building proper breadcrumb in admin
        "opts": opts,
        "action_checkbox_name": helpers.ACTION_CHECKBOX_NAME,
        "media": media,
    }

    request.current_app = modeladmin.admin_site.name

    # Display the confirmation page
    return TemplateResponse(
        request,
        modeladmin.delete_selected_confirmation_template
        or [
            "admin/%s/%s/delete_selected_confirmation.html"
            % (app_label, opts.model_name),
            "admin/%s/delete_selected_confirmation.html" % app_label,
            "admin/delete_selected_confirmation.html",
        ],
        context,
    )
