from django import forms
from django.http import Http404
from django.forms import ValidationError
from crispy_forms.helper import FormHelper

from crispy_forms.layout import Layout, Div, HTML
from bytedeck_summernote.widgets import ByteDeckSummernoteSafeInplaceWidget, ByteDeckSummernoteAdvancedInplaceWidget
from comments.models import Comment

from utilities.fields import FILE_MIME_TYPES, RestrictedFileFormField

from .models import Question, QuestionSubmission


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


class QuestionSubmissionForm(forms.ModelForm):
    """Displayed to the student when they are answering a question.

    Multiple of these forms are displayed in an inline formset, one for each question.
    They are all grouped together under a single comment.
    """

    # for some reason, if I don't include this, an ID field would be present in the form
    # why is this?
    id = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    class Meta:
        model = QuestionSubmission
        fields = (
            "id",
            "comment",
            "response_text",
            "response_file",
        )

    def __init__(self, *args, **kwargs):
        """Change the form fields based on the question type

        Raises:
            ValueError: Raised if the question_type provided is not one of the supported types,
            or if the QuestionSubmission instance does not have a Question.
        """
        super().__init__(*args, **kwargs)

        self.question = self.instance.question
        if not self.question:
            raise ValueError("QuestionSubmissionForm requires a QuestionSubmission instance with a Question.")

        form_fields = Div("response_text")
        if self.question.type == "short_answer":
            del self.fields["response_file"]
            self.fields["response_text"].required = self.question.required
            self.fields["response_text"].widget.attrs.update({'maxlength': '200'})
            # make the charfield smaller
            self.fields["response_text"].widget.attrs.update({'rows': '2'})
        elif self.question.type == "long_answer":
            del self.fields["response_file"]
            self.fields["response_text"] = forms.CharField(
                label="", required=self.question.required, widget=ByteDeckSummernoteSafeInplaceWidget()
            )
        elif self.question.type == "file_upload":
            del self.fields["response_text"]
            file_types = FILE_MIME_TYPES[self.question.allowed_file_type]
            filetypes_help_text = f"Allowed file types: {self.question.allowed_file_type.capitalize()}"

            self.fields["response_file"] = RestrictedFileFormField(
                required=self.question.required,
                content_types=file_types,
                max_upload_size=16777216,
                widget=forms.ClearableFileInput(attrs={"multiple": False}),
                label="Attach files",
                help_text=filetypes_help_text,
            )

            file_types_popover = f"""
            <a data-toggle="popover"
               data-trigger="hover"
               data-placement="auto"
               title="All Allowed File Types"
               data-content="{', '.join(file_types)}">
                <i class="fa fa-fw fa-lg fa-info-circle"></i>
            </a>
            """

            form_fields = Div("response_file",
                              HTML(file_types_popover))
        else:
            raise NotImplementedError(
                f"Question of type {self.question.type} not supported yet."
            )

        form_fields.css_class = 'form-group'

        self.instructions_label = HTML(
            "<p><strong>Instructions</strong>: {{ form.question.instructions|safe|default:'-'}}</p>"
        )

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        self.helper.layout = Layout(
            "id",
            "comment",
            self.instructions_label,
            form_fields
        )

    def clean(self):
        cleaned_data = super().clean()

        response_text = cleaned_data.get('response_text')
        response_file = cleaned_data.get('response_file')

        if self.question.type in ["short_answer", "long_answer"]:
            if self.question.required and not response_text:
                raise ValidationError('You must provide a text response for this type of question.')
        elif self.question.type == "file_upload":
            if self.question.required and not response_file:
                raise ValidationError('You must upload a file for this type of question.')
        else:
            raise NotImplementedError(f'Question of type {self.question.type} not supported yet.')

        return cleaned_data


QuestionSubmissionFormsetFactory = forms.inlineformset_factory(
    Comment,
    QuestionSubmission,
    QuestionSubmissionForm,
    # the number of forms should exactly match the number of questions
    extra=0,
    can_delete=False,
)
