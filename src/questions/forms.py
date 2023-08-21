from django import forms
from django.http import Http404
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, HTML

from utilities.fields import FILE_MIME_TYPES
from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedInplaceWidget

from .models import Question


class QuestionForm(forms.ModelForm):
    """Displayed to the teacher when they are creating a question.
    Used for creating and editing Question instances.
    """

    class Meta:
        model = Question

        fields = ('type',
                  'required',
                  'instructions',
                  'solution_text',
                  'solution_file',
                  'allowed_file_type',
                  'marker_notes')

        # hide question_type
        widgets = {
            'type': forms.HiddenInput(),
            'instructions': ByteDeckSummernoteAdvancedInplaceWidget(),
            'solution_text': forms.Textarea(attrs={'rows': 2}),
            'marker_notes': ByteDeckSummernoteAdvancedInplaceWidget(),
        }

    def __init__(self, *args, **kwargs):
        """Change the form fields based on the question type

        Raises:
            ValueError: Raised if the question_type provided is not one of the supported types
        """

        question_type = kwargs.pop('question_type', None)

        # initialize the form normally, without the two values we just popped
        super().__init__(*args, **kwargs)

        if question_type == 'short_answer':
            del self.fields['solution_file']
            del self.fields['allowed_file_type']
            solution_fields = Div('solution_text')
            # set question_type to short_answer
        elif question_type == 'long_answer':
            del self.fields['solution_file']
            del self.fields['allowed_file_type']
            solution_fields = Div('solution_text')
        elif question_type == 'file_upload':
            del self.fields['solution_text']

            allowed_file_types_html_list = ''
            # add additional information about the allowed file types for each option
            for choice, verbose_name in self.fields['allowed_file_type'].choices:
                # at this point, it only makes sense to show the allowed file types for these options
                if choice in ['image', 'audio', 'video']:
                    if isinstance(FILE_MIME_TYPES[choice], list):
                        allowed_file_mime_types = ', '.join(FILE_MIME_TYPES[choice])
                    else:
                        allowed_file_mime_types = FILE_MIME_TYPES[choice]
                    allowed_file_types_html_list += f"<li><strong>{verbose_name.capitalize()}</strong>: {allowed_file_mime_types}</li>"

            solution_fields = Div(
                'solution_file',
                'allowed_file_type',
                HTML(f"""
                    <p><strong>Allowed File Types Legend:</strong></p>
                     <ul>
                     {allowed_file_types_html_list}
                     </ul>
                     """)
            )

        else:
            raise Http404(f"Question of type {question_type} not supported.")

        self.fields['type'].initial = question_type

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            Div(
                Div(
                    'type',
                    'required',
                    'instructions',
                    solution_fields,
                    'marker_notes',
                    css_class='form-group'
                )
            )
        )
