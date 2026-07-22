from django import forms
from django.forms import ValidationError

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, HTML

from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedInplaceWidget, ByteDeckSummernoteSafeInplaceWidget
from quest_manager.models import QuestSubmission
from utilities.fields import FILE_MIME_TYPES, RestrictedFileFormField

from .models import Question, QuestionSubmission, QuestionType

# 16 MiB, the maximum size of a student's file response.
MAX_RESPONSE_FILE_SIZE = 16 * 1024 * 1024


class QuestionForm(forms.ModelForm):
    """Displayed to the teacher when they are creating or editing a Question.

    The form's fields depend on the question type (a short_answer question has no file-related
    fields, a file_upload question has no solution_text, etc.), so the ``question_type`` kwarg
    is mandatory. Views are responsible for validating the type from the URL (and 404ing on
    unknown values) before constructing the form.
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

        # type comes from the URL and is fixed per form, so it is hidden
        widgets = {
            'type': forms.HiddenInput(),
            'instructions': ByteDeckSummernoteAdvancedInplaceWidget(),
            'solution_text': forms.Textarea(attrs={'rows': 2}),
            'marker_notes': ByteDeckSummernoteAdvancedInplaceWidget(),
        }

    def __init__(self, *args, **kwargs):
        """Build the form for the given ``question_type`` kwarg, hiding the fields that
        don't apply to that type.

        Raises:
            ValueError: If ``question_type`` is not one of the supported types. Callers
                (views) must validate user-supplied types first — by the time the form is
                constructed an unknown type is a programming error.
        """
        question_type = kwargs.pop('question_type', None)

        # initialize the form normally, without the value we just popped
        super().__init__(*args, **kwargs)

        if question_type in (QuestionType.SHORT_ANSWER, QuestionType.LONG_ANSWER):
            del self.fields['solution_file']
            del self.fields['allowed_file_type']
            solution_fields = Div('solution_text')
        elif question_type == QuestionType.FILE_UPLOAD:
            del self.fields['solution_text']

            # add additional information about the allowed MIME types for each option
            allowed_file_types_html_list = ''
            for choice, verbose_name in self.fields['allowed_file_type'].choices:
                mime_types = FILE_MIME_TYPES.get(choice)
                # 'all' (and any non-list sentinel) accepts everything, so a legend row is pointless
                if isinstance(mime_types, list):
                    allowed_file_types_html_list += f"<li><strong>{verbose_name}</strong>: {', '.join(mime_types)}</li>"

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
            raise ValueError(f"Question of type {question_type} not supported.")

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
    """Displayed to the student when they are answering a single Question.

    Multiple of these forms are displayed in an inline formset (one per question), all owned by
    the student's QuestSubmission. The response field shown depends on the question's type.

    If the answer's Question has been deleted (question=None via SET_NULL), the form degrades to
    a stub that fails validation with a friendly message instead of crashing: callers should
    normally exclude such rows from the formset queryset (``question__isnull=False``), so the
    stub only appears when the page's data went stale mid-edit (e.g. a teacher deleted a
    question between page load and POST).
    """

    class Meta:
        model = QuestionSubmission
        fields = (
            "response_text",
            "response_file",
        )

    def __init__(self, *args, **kwargs):
        """Build the response field appropriate to the instance's question type."""
        super().__init__(*args, **kwargs)

        self.question = self.instance.question if self.instance.question_id else None

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        # the formset machinery adds a hidden 'id' (pk) field to each form; it must be
        # rendered so a POST can match each answer back to its row
        self.helper.render_hidden_fields = True

        if self.question is None:
            # Degraded stub (question deleted or instance missing): no response fields,
            # clean() reports the problem instead of a 500.
            del self.fields["response_text"]
            del self.fields["response_file"]
            self.helper.layout = Layout()
            return

        form_fields = Div("response_text")
        if self.question.type == QuestionType.SHORT_ANSWER:
            del self.fields["response_file"]
            # replace the model's TextField default with a CharField so the 200-character
            # limit is enforced server-side, not just by the widget's maxlength attribute
            self.fields["response_text"] = forms.CharField(
                label="Response text",
                required=self.question.required,
                max_length=200,
                widget=forms.Textarea(attrs={'maxlength': '200', 'rows': '2'}),
            )
        elif self.question.type == QuestionType.LONG_ANSWER:
            del self.fields["response_file"]
            self.fields["response_text"] = forms.CharField(
                label="", required=self.question.required, widget=ByteDeckSummernoteSafeInplaceWidget()
            )
        elif self.question.type == QuestionType.FILE_UPLOAD:
            del self.fields["response_text"]
            mime_types = self.question.allowed_mime_types()

            self.fields["response_file"] = RestrictedFileFormField(
                required=self.question.required,
                content_types=mime_types,
                max_upload_size=MAX_RESPONSE_FILE_SIZE,
                widget=forms.ClearableFileInput(attrs={"multiple": False}),
                label="Attach files",
                help_text=f"Allowed file types: {self.question.get_allowed_file_type_display()}",
            )

            form_fields = Div("response_file")
            if isinstance(mime_types, list):
                # 'all' has no meaningful MIME list to show ("All" sentinel), so the
                # popover enumerating exact MIME types only appears for restricted choices
                file_types_popover = f"""
                <a data-toggle="popover"
                   data-trigger="hover"
                   data-placement="auto"
                   title="All Allowed File Types"
                   data-content="{', '.join(mime_types)}">
                    <i class="fa fa-fw fa-lg fa-info-circle"></i>
                </a>
                """
                form_fields = Div("response_file", HTML(file_types_popover))
        else:
            raise NotImplementedError(
                f"Question of type {self.question.type} not supported yet."
            )

        form_fields.css_class = 'form-group'

        # The question's instructions (teacher-authored summernote HTML) shown above the response field
        instructions_label = HTML(
            "<p><strong>Instructions</strong>: {{ form.question.instructions|safe|default:'-'}}</p>"
        )

        self.helper.layout = Layout(
            instructions_label,
            form_fields,
        )

    def clean(self):
        """Enforce required answers per question type, and fail cleanly on stale rows."""
        cleaned_data = super().clean()

        if self.question is None:
            raise ValidationError(
                "This answer no longer matches one of the quest's questions. Please reload the page and try again."
            )

        response_text = cleaned_data.get('response_text')
        response_file = cleaned_data.get('response_file')

        if self.question.type in (QuestionType.SHORT_ANSWER, QuestionType.LONG_ANSWER):
            if self.question.required and not response_text:
                raise ValidationError('You must provide a text response for this type of question.')
        else:
            # only FILE_UPLOAD can reach here: __init__ raises NotImplementedError for any other type
            if self.question.required and not response_file:
                raise ValidationError('You must upload a file for this type of question.')

        return cleaned_data


QuestionSubmissionFormsetFactory = forms.inlineformset_factory(
    QuestSubmission,
    QuestionSubmission,
    QuestionSubmissionForm,
    # the number of forms should exactly match the number of questions, which the
    # caller provides via the queryset; students can never add or remove rows
    extra=0,
    can_delete=False,
)
