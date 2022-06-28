from dal import autocomplete
from crispy_forms.helper import FormHelper
from crispy_forms import layout

from django.core.exceptions import FieldDoesNotExist
from django.contrib.contenttypes.fields import GenericForeignKey

from prerequisites.models import IsAPrereqMixin, Prereq


def popover_labels(model, field_strings):
    fields_html = {}
    for field_string in field_strings:
        try:
            field = model._meta.get_field(field_string)
        except FieldDoesNotExist:
            continue  # if custom field we skip it
        
        if type(field) == GenericForeignKey:
            continue  # if generic foreign key we skip it, it doesn't have these attributes

        html = field.verbose_name
        if(field.help_text != ""):
            html += ' <i class="fa fa-question-circle-o text-info" data-toggle="tooltip" data-placement="top" title="' + field.help_text + '"></i> '
        fields_html[field.name] = html
    return fields_html


def generate_prereq_model_choice(): 
    """A list of tuples: [(model, model_search_field), ...] for DAL widgets"""
    models = IsAPrereqMixin.all_registered_model_classes()
    model_choices = [(model, model.dal_autocomplete_search_fields()) for model in models]
    return model_choices


class PrereqFormInline(autocomplete.FutureModelForm):
    """This form class is intended to be used in an inline formset"""

    prereq_object = autocomplete.Select2GenericForeignKeyModelField(
        model_choice=generate_prereq_model_choice(),
        # field_id='prerequisite',
    )

    or_prereq_object = autocomplete.Select2GenericForeignKeyModelField(
        model_choice=generate_prereq_model_choice(),
    )

    class Meta:
        model = Prereq
        # fields = ['prereq_content_type', 'prereq_object_id', 'prereq_count', 'prereq_invert']
        fields = ['prereq_object', 'prereq_count', 'prereq_invert', 'or_prereq_object', 'or_prereq_count', 'or_prereq_invert']
        help_texts = {field: None for field in fields}
        labels = {
            'prereq_count': "Count",
            'or_prereq_count': "Count",
            'or_prereq_invert': "NOT",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['prereq_object'].widget.attrs['data-placeholder'] = 'Type to search'
        self.fields['or_prereq_object'].widget.attrs['data-placeholder'] = 'Type to search'
        self.fields['prereq_object'].label = "Required Element"
        self.fields['or_prereq_object'].label = "Alternate Element"
        self.fields['or_prereq_object'].required = False


class PrereqFormsetHelper(FormHelper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # self.helper.form_class = 'form-inline'
        self.template = 'bootstrap/table_inline_formset.html'
        self.form_id = "id_prereq_formset"
        self.add_input(layout.Submit("submit", "Save", css_class='btn-success'))
        self.add_input(layout.Submit("cancel", "Cancel", css_class='btn-danger'))
