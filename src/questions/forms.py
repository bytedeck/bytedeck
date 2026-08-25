from django import forms
from django.forms import ValidationError
from django.utils.safestring import mark_safe

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Div, HTML

from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedInplaceWidget, ByteDeckSummernoteSafeInplaceWidget
from comments.sanitize import sanitize_comment_html
from quest_manager.models import QuestSubmission
from utilities.fields import FILE_MIME_TYPES, RestrictedFileFormField
from utilities.html import is_empty_html

from .models import Question, QuestionSubmission, QuestionType

# 16 MiB, the maximum size of a student's file response.
MAX_RESPONSE_FILE_SIZE = 16 * 1024 * 1024

# How many characters a student may type into a short answer. One number for the field's
# validation, the input's maxlength and the help text that tells the student, so what they
# are told and what they are held to cannot drift apart (#2401).
SHORT_ANSWER_MAX_LENGTH = 200


class AnswerSummernoteWidget(ByteDeckSummernoteSafeInplaceWidget):
    """A long-answer editor sized for one answer among several on the submission page.

    The site-wide editor height suits a page with one editor on it. A quest can ask several long
    answers, and each one arrives above the submission's own comment editor, so at that height a
    three-question quest is metres of scrolling before the student reaches the submit button
    (#2169). The editor still grows as the student types past the bottom.
    """

    # ~5 lines of typing before the editor scrolls, against the site-wide 480
    ANSWER_EDITOR_HEIGHT = "180"

    def summernote_settings(self):
        """Return the site-wide summernote settings with the shorter answer height.

        Returns:
            dict: the settings the widget's template hands to summernote.
        """
        settings = super().summernote_settings()
        settings["height"] = self.ANSWER_EDITOR_HEIGHT
        return settings


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
        """Build the answer field and crispy layout for the instance's question type.

        A short answer gets a length-capped text input, a long answer a rich-text editor sized
        for a page that stacks several of them, and a file upload a type-restricted file field.
        A row whose question has been deleted gets no answer field at all, and clean() reports
        that instead of raising. The layout skips its own media, since the submission page
        already loads the editor assets for its comment box.

        Args:
            *args: positional arguments for the ModelForm (data, files, ...).
            **kwargs: keyword arguments for the ModelForm; ``instance`` carries the answer row
                whose question decides the field.
        """
        super().__init__(*args, **kwargs)

        self.question = self.instance.question if self.instance.question_id else None

        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True
        # the formset machinery adds a hidden 'id' (pk) field to each form; it must be
        # rendered so a POST can match each answer back to its row
        self.helper.render_hidden_fields = True
        # A long answer's editor would otherwise emit the whole summernote asset set again,
        # mid-page, on top of the copy the submission page's own comment editor already loads
        # in the head (#2169).
        self.helper.include_media = False

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
            # replace the model's TextField default with a CharField so the 200-character limit
            # on the raw text the student types is enforced server-side, not just by the widget's
            # maxlength attribute. The cap is on the raw input (validated before clean_response_text
            # runs); see that method for why the stored value can be longer (#2170).
            # A short answer is a single line, so use a text input (not a textarea).
            # no visible label (the question's instructions directly above serve as the label,
            # matching the long answer field); a distinct aria-label per question keeps each
            # input tellable apart for screen-reader users when a page has several short answers.
            # The help text is where the student learns the limit: the input enforces it
            # silently, by refusing keystrokes once the answer is full (#2401).
            self.fields["response_text"] = forms.CharField(
                label="",
                required=self.question.required,
                max_length=SHORT_ANSWER_MAX_LENGTH,
                help_text=f"Up to {SHORT_ANSWER_MAX_LENGTH} characters.",
                widget=forms.TextInput(attrs={
                    'maxlength': str(SHORT_ANSWER_MAX_LENGTH),
                    'aria-label': self._response_aria_label(),
                }),
            )
        elif self.question.type == QuestionType.LONG_ANSWER:
            del self.fields["response_file"]
            self.fields["response_text"] = forms.CharField(
                label="", required=self.question.required, widget=AnswerSummernoteWidget()
            )
        elif self.question.type == QuestionType.FILE_UPLOAD:
            del self.fields["response_text"]
            mime_types = self.question.allowed_mime_types()

            help_text = f"Allowed file types: {self.question.get_allowed_file_type_display()}"
            if isinstance(mime_types, list):
                # 'all' has no meaningful MIME list to show ("All" sentinel), so the
                # popover enumerating exact MIME types only appears for restricted choices.
                # It rides inside the help text so the icon sits on the same line as the types
                # it explains, rather than on a line of its own below them.
                help_text = mark_safe(help_text + f"""
                <a data-toggle="popover"
                   data-trigger="hover"
                   data-placement="auto"
                   title="All Allowed File Types"
                   data-content="{', '.join(mime_types)}">
                    <i class="fa fa-fw fa-lg fa-info-circle"></i>
                </a>
                """)

            self.fields["response_file"] = RestrictedFileFormField(
                required=self.question.required,
                content_types=mime_types,
                max_upload_size=MAX_RESPONSE_FILE_SIZE,
                widget=forms.ClearableFileInput(attrs={"multiple": False}),
                label="Attach files",
                help_text=help_text,
            )

            form_fields = Div("response_file")
        else:
            raise NotImplementedError(
                f"Question of type {self.question.type} not supported yet."
            )

        form_fields.css_class = 'form-group'

        # The question's instructions (teacher-authored summernote HTML) are rendered by the
        # including template (submission.html) on the same line as the "Question N" heading, so
        # the layout here is just the answer field.
        self.helper.layout = Layout(
            form_fields,
        )

    def _response_aria_label(self):
        """Return a per-question aria-label for the short-answer input.

        Several short-answer inputs on one page would otherwise all announce the identical
        "Response", so screen-reader users couldn't tell them apart. The form's formset prefix
        is "question_submissions-<i>" (0-based); i + 1 matches the visible "Question N:" heading
        rendered just above the input in submission.html. Falls back to "Response" if the form
        isn't in a formset (no numeric prefix, e.g. the formset's empty_form placeholder).

        Returns:
            str: the aria-label for this input, e.g. "Response to question 2".
        """
        try:
            position = int(self.prefix.rsplit("-", 1)[-1]) + 1
        except (AttributeError, ValueError):
            return "Response"
        return f"Response to question {position}"

    def clean_response_text(self):
        """Sanitize the answer text with the comments allow-list (issue #1343 / #2113).

        Answers are rendered with |safe in the marking display, and neither input path is
        safe on its own: the plain short answer textarea accepts anything, and the "safe"
        summernote widget filters tags but allows every attribute (so onclick etc. survive).
        Sanitizing here keeps legitimate formatting while stripping script vectors, matching
        how comment text is handled.

        The short-answer 200-character limit is on the *raw* text the student types: the
        CharField's max_length is validated before this runs, matching the input's maxlength,
        so the student can never type more than 200 characters. HTML-escaping here (``<`` ->
        ``&lt;``, ``&`` -> ``&amp;``) can make the *stored* value longer than 200, but that
        escaped value renders back to the same <=200 typed characters via |safe, so the
        advertised limit still holds from the student's point of view. Capping the escaped
        length instead would reject <=200-character answers the browser accepted (e.g. one
        with a few ``<``/``&``), which would be a confusing client/server mismatch (#2170).

        Returns:
            str: the answer with dangerous HTML removed, ready to store and render with |safe.
        """
        return sanitize_comment_html(self.cleaned_data.get("response_text", ""))

    def has_answer(self):
        """Whether the student actually answered this question.

        The single definition of "answered", so the required check below and the complete
        view's decision about whether a submission has any content of its own cannot drift
        apart and disagree about the same answer.

        A long answer comes from the Summernote editor, which posts markup rather than an
        empty string for an untouched editor, so emptiness there is a question about what the
        markup renders as (#2560). The other two types have no such gap: a short answer is a
        plain text input whose CharField already strips whitespace-only input, and a file is
        either attached or it isn't.

        Only call this once validation has run: it reads ``cleaned_data``, and a field that
        failed its own validation is absent from it and so reads as unanswered.

        Returns:
            bool: True when this form carries an answer with content in it.
        """
        if self.question.type == QuestionType.FILE_UPLOAD:
            return bool(self.cleaned_data.get("response_file"))

        response_text = self.cleaned_data.get("response_text")
        if self.question.type == QuestionType.LONG_ANSWER:
            return not is_empty_html(response_text)
        return bool(response_text)

    def clean(self):
        """Enforce required answers per question type, and fail cleanly on stale rows."""
        cleaned_data = super().clean()

        if self.question is None:
            raise ValidationError(
                "This answer no longer matches one of the quest's questions. Please reload the page and try again."
            )

        if self.question.required and not self.has_answer():
            if self.question.type == QuestionType.FILE_UPLOAD:
                raise ValidationError('You must upload a file for this type of question.')
            raise ValidationError('You must provide a text response for this type of question.')

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
