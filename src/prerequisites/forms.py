from crispy_forms.helper import FormHelper
from crispy_forms import layout

from django.core.exceptions import FieldDoesNotExist
from django.contrib.contenttypes.fields import GenericForeignKey


from utilities.forms import FutureModelForm
from utilities.fields import AllowedGFKChoiceField

from .models import Prereq


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
        if field.help_text != "":
            html += ' <i class="fa fa-question-circle-o text-info" data-toggle="tooltip" data-placement="top" title="' + field.help_text + '"></i> '
        fields_html[field.name] = html
    return fields_html


class PrereqGFKChoiceField(AllowedGFKChoiceField):
    """
    Can't always dynamically load this list due to accessing contenttypes too early
    So instead provide a hard coded list which is checked during testing to ensure it matches
    what the dynamically loaded list would have produced
    """
    def get_allowed_model_classes(self):
        return Prereq.all_registered_model_classes()


class PrereqFormInline(FutureModelForm):
    """This form class is intended to be used in an inline formset"""

    prereq_object = PrereqGFKChoiceField()

    or_prereq_object = PrereqGFKChoiceField(required=False)

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
        self.fields['prereq_object'].label = "Required Element"
        self.fields['or_prereq_object'].label = "Alternate Element"

        count_attrs = {
            'class': 'form-control',
            'style': 'width: 50px;'
        }
        self.fields['prereq_count'].widget.attrs.update(count_attrs)
        self.fields['or_prereq_count'].widget.attrs.update(count_attrs)


class PrereqFormsetHelper(FormHelper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # self.helper.form_class = 'form-inline'
        self.template = 'bootstrap/table_inline_formset.html'
        self.form_id = "id_prereq_formset"
        self.add_input(layout.Submit("submit", "Save", css_class='btn-success'))
        self.add_input(layout.Submit("cancel", "Cancel", css_class='btn-danger'))
