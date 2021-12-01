from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.contenttypes.admin import GenericTabularInline

# from tenant.admin import NonPublicSchemaOnlyAdminAccessMixin

from .models import Prereq
from .tasks import update_quest_conditions_all_users


class PrereqInlineForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super(PrereqInlineForm, self).__init__(*args, **kwargs)

        # only include models 'registered' with the prerequisites app
        self.fields['prereq_content_type'].queryset = Prereq.all_registered_content_types()
        self.fields['or_prereq_content_type'].queryset = Prereq.all_registered_content_types()


class PrereqInline(GenericTabularInline):
    model = Prereq
    ct_field = "parent_content_type"
    ct_fk_field = "parent_object_id"
    fk_name = "parent_object"
    form = PrereqInlineForm

    extra = 1

    exclude = ['name', ]

    autocomplete_lookup_fields = {
        'generic': [
            ['prereq_content_type', 'prereq_object_id'],
            ['or_prereq_content_type', 'or_prereq_object_id'],
        ]
    }


def auto_name_selected_prereqs(modeladmin, request, queryset):
    for prereq in queryset:
        prereq.name = str(prereq)
        prereq.save()


def recalculate_available_quests_for_all_users(modeladmin, request, queryset):
    update_quest_conditions_all_users.apply_async(args=[1], queue='default', countdown=settings.CONDITIONS_UPDATE_COUNTDOWN)
    messages.add_message(
        request, messages.INFO, 
        'Recalculating... this might take a while so I\'m doing it the background. You don\'t need to stick around and can leave this page.'
    )


# class PrereqAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
#     list_display = ('id', 'parent', '__str__', 'name')
#     actions = [auto_name_selected_prereqs]


# class PrereqAllConditionsMetAdmin(NonPublicSchemaOnlyAdminAccessMixin, admin.ModelAdmin):
#     list_display = ('id', 'user_id', 'model_name')
#     actions = [recalculate_available_quests_for_all_users]


# admin.site.register(Prereq, PrereqAdmin)
# admin.site.register(PrereqAllConditionsMet, PrereqAllConditionsMetAdmin)
