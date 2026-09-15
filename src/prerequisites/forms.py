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
    """Lays out the prereq formset as a table of rows, with the controls that save it,
    abandon it, and add another row to it.
    """

    def __init__(self, *args, **kwargs):
        """Set up that layout: the crispy template the formset renders through, the form id the
        add-row script selects on, and the controls rendered under the table. Takes and passes
        on FormHelper's own arguments; a configured helper is the result.
        """
        super().__init__(*args, **kwargs)

        # self.helper.form_class = 'form-inline'
        # crispy-forms 2.x dropped the bundled bootstrap(2) pack; this template
        # now comes from the crispy-bootstrap3 package
        self.template = 'bootstrap3/table_inline_formset.html'
        self.form_id = "id_prereq_formset"
        self.add_input(layout.Submit("submit", "Save", css_class='btn-success'))
        self.add_input(layout.Submit("cancel", "Cancel", css_class='btn-danger'))
        # The control that appends another blank row to the formset, so a teacher can add more
        # prerequisites than the one spare row the formset renders. It is one of the helper's
        # inputs, which is what puts it alongside Save and Cancel wherever the template pack
        # renders those: nothing outside the helper needs to know that markup. The script on
        # advanced_prereqs_form.html only binds its click handler. Issue #2707.
        self.add_input(layout.Button("add-form", "Add Another Prerequisite", css_id="add-form", css_class='btn-primary'))
