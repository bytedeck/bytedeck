from crispy_forms.helper import FormHelper
from crispy_forms import layout

from utilities.forms import FutureModelForm
from utilities.fields import AllowedGFKChoiceField

from .models import Prereq


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

    class Media:
        # Fixes the crispy-bootstrap3 checkbox layout on the advanced prereqs form (issue #1978).
        # Kept with the form (rather than inline in the template) so it loads via {{ form.media.css }}.
        css = {'all': ('prerequisites/css/advanced_prereqs_form.css',)}

    # prereq_object / or_prereq_object are the Prereq model's GenericForeignKeys,
    # declared above as form fields and persisted by FutureModelForm (via the
    # field's save_object_data()). They are intentionally NOT listed in
    # Meta.fields: since Django 5.0, naming a non-editable model field (a GFK) in
    # Meta.fields raises FieldError instead of silently ignoring it. Because
    # declared fields not in Meta.fields are appended after the model fields,
    # field_order restores the original interleaved column order for the formset.
    field_order = ['prereq_object', 'prereq_count', 'prereq_invert', 'or_prereq_object', 'or_prereq_count', 'or_prereq_invert']

    class Meta:
        model = Prereq
        fields = ['prereq_count', 'prereq_invert', 'or_prereq_count', 'or_prereq_invert']
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
        # crispy-forms 2.x dropped the bundled bootstrap(2) pack; this template
        # now comes from the crispy-bootstrap3 package
        self.template = 'bootstrap3/table_inline_formset.html'
        self.form_id = "id_prereq_formset"
        self.add_input(layout.Submit("submit", "Save", css_class='btn-success'))
        self.add_input(layout.Submit("cancel", "Cancel", css_class='btn-danger'))
