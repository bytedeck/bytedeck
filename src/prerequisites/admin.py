from django import forms
from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
# from django.contrib.contenttypes.models import ContentType

from .models import Prereq, PrereqAllConditionsMet


# Register your models here.

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


class PrereqAdmin(admin.ModelAdmin):
    list_display = ('id', 'parent', '__str__', 'name')
    actions = [auto_name_selected_prereqs]


admin.site.register(Prereq, PrereqAdmin)


class PrereqAllConditionsMetAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id', 'model_name')


admin.site.register(PrereqAllConditionsMet, PrereqAllConditionsMetAdmin)
