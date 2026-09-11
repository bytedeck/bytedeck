from django import forms
from django.core.exceptions import ValidationError

from bootstrap_datepicker_plus.widgets import DatePickerInput, TimePickerInput
from crispy_forms.bootstrap import Accordion, AccordionGroup
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout
from django_select2.forms import ModelSelect2MultipleWidget, ModelSelect2Widget

from badges.models import Badge
from bytedeck_summernote.widgets import ByteDeckSummernoteSafeInplaceWidget, ByteDeckSummernoteAdvancedInplaceWidget
from comments.sanitize import sanitize_comment_html
from utilities.fields import RestrictedMultiFileFormField
from tags.forms import BootstrapTaggitSelect2Widget

from courses.forms import XPCourseChoiceMixin
from courses.models import Course

from .models import Category, Quest, CommonData


#: Quest fields a student TA may not set. A TA works on drafts, so whether a quest is
#: visible to students (``published``), who may keep editing it (``editor``), whether it is
#: filed away (``archived``) and whether it escapes course enrolment
#: (``available_outside_course``) all stay with the teacher.
TA_RESTRICTED_QUEST_FIELDS = ('published', 'editor', 'archived', 'available_outside_course')


def remove_layout_fields(layout_object, field_names):
    """Remove the named fields from a crispy-forms layout tree, in place.

    Used when a form subclass drops fields the shared layout still names, so crispy is
    never asked to render a field the form does not have.

    Args:
        layout_object: a crispy ``Layout`` (or any nested layout object). Objects without
            a ``fields`` list, such as ``HTML``, are left alone.
        field_names: an iterable of field names to drop wherever they appear in the tree.

    Returns:
        None. The layout is modified in place.
    """
    fields = getattr(layout_object, 'fields', None)
    if fields is None:
        return

    layout_object.fields = [
        field for field in fields
        if not (isinstance(field, str) and field in field_names)
    ]
    for child in layout_object.fields:
        remove_layout_fields(child, field_names)


class BadgeLabel:
    def label_from_instance(self, obj):
        return f"{str(obj)} ({obj.xp} XP)"


class BadgeSelect2MultipleWidget(BadgeLabel, ModelSelect2MultipleWidget):

    def __init__(self, *args, **kwargs):
        """ Despite what Select2 and django-select2 docs tell you. You cant actually change the default setting in javascript.
        For now modify the `attrs` variable to set default attributes
        """
        attrs = kwargs.get('attrs', {})
        # As of `django-select2 7.1.2`, Select2 by default now has a minimum input length of 2.
        attrs.setdefault('data-minimum-input-length', '0')
        kwargs['attrs'] = attrs

        super().__init__(*args, **kwargs)


class QuestForm(forms.ModelForm):

    new_quest_prerequisite = forms.ModelChoiceField(
        # to_field_name="name",
        required=False,
        queryset=Quest.objects.all(),
        widget=ModelSelect2Widget(
            model=Quest,
            search_fields=['name__icontains'],
            attrs={'data-minimum-input-length': 0, 'data-theme': 'bootstrap'},
        ),
    )

    new_badge_prerequisite = forms.ModelChoiceField(
        # to_field_name="name",
        required=False,
        queryset=Badge.objects.all(),
        widget=ModelSelect2Widget(
            model=Badge,
            search_fields=['name__icontains'],
            attrs={'data-minimum-input-length': 0, 'data-theme': 'bootstrap'},
        ),
    )

    campaign = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        limit_choices_to={'published': True}
    )

    class Meta:
        model = Quest
        fields = ('name', 'published', 'xp', 'xp_can_be_entered_by_students', 'icon', 'short_description',
                  'verification_required', 'instructions',
                  'campaign', 'common_data', 'submission_details', 'instructor_notes', 'quick_reply',
                  'repeat_per_semester', 'max_repeats', 'max_xp', 'hours_between_repeats',
                  'map_transition', 'tags',
                  'new_quest_prerequisite',
                  'new_badge_prerequisite',
                  'specific_teacher_to_notify', 'blocking',
                  'hideable', 'sort_order', 'date_available', 'time_available', 'date_expired', 'time_expired',
                  'available_outside_course', 'archived', 'editor')

        date_options = {
            'showMeridian': False,
            # 'todayBtn': True,
            'todayHighlight': True,
            # 'minuteStep': 5,
            'pickerPosition': 'bottom-left',
        }

        time_options = {
            'pickerPosition': 'bottom-left',
            'maxView': 0,
        }

        widgets = {
            'instructions': ByteDeckSummernoteAdvancedInplaceWidget(),
            'submission_details': ByteDeckSummernoteAdvancedInplaceWidget(),
            'instructor_notes': ByteDeckSummernoteAdvancedInplaceWidget(),

            'date_available': DatePickerInput(),

            'time_available': TimePickerInput(),
            'date_expired': DatePickerInput(),
            'time_expired': TimePickerInput(),

            # TODO: Campaign Autocomplete
            # 'campaign': autocomplete.ModelSelect2(url='quests:category_autocomplete'),
            # 'common_data': autocomplete.ModelSelect2(url='quests:commondata_autocomplete'),
            # 'specific_teacher_to_notify': Select2Widget(),

            # dal widgets aren't compatible with django-select2 widget.  Need to convert all to dal.
            'tags': BootstrapTaggitSelect2Widget(attrs={'data-theme': 'bootstrap'})
        }

    def __init__(self, *args, **kwargs):
        """Build the quest form's crispy layout.

        Beyond the model fields, the layout carries the form's action buttons (cancel and submit,
        repeated top and bottom) and links out to the two parts of a quest configured on their own
        pages: prerequisites and submission questions. Both of those need a saved quest to attach
        to, so on the create form they render as disabled placeholders explaining why.

        Args:
            *args: positional arguments passed through to ``forms.ModelForm``.
            **kwargs: keyword arguments passed through to ``forms.ModelForm``.
        """
        super().__init__(*args, **kwargs)

        self.fields['common_data'].label = 'Common Quest Info'
        self.fields['common_data'].queryset = CommonData.objects.filter(active=True)

        cancel_btn = '<a href="{{ cancel_url }}" role="button" class="btn btn-danger">Cancel</a> '
        submit_btn = '<input type="submit" value="{{ submit_btn_value }}" class="btn btn-success"/> '

        prereqs_btn = '{% if object.id %}<a role="button" class="btn btn-default" href="{% url \'quests:quest_prereqs_update\' object.id %}">' \
            'Edit Prerequisites</a>' \
            '{% else %}<button type="button" class="btn btn-default" disabled title="You need to create this new quest first, ' \
            'before you can add prerequisites.">Edit Prerequisites</button>' \
            '{% endif %} '

        # Questions are managed on their own page, so link to it from the form where the rest of
        # the quest is configured (#2347); the detail page's "Submission Questions" panel is the
        # other way in. Staff-only, because every view in the questions app requires staff and
        # TAQuestForm inherits this layout, so an unguarded button would 403 for a TA.
        questions_btn = '{% if request.user.is_staff %}' \
            '{% if object.id %}<a role="button" class="btn btn-default" href="{% url \'questions:list\' object.id %}">' \
            'Manage Questions</a>' \
            '{% else %}<button type="button" class="btn btn-default" disabled title="You need to create this new quest first, ' \
            'before you can add submission questions.">Manage Questions</button>' \
            '{% endif %}' \
            '{% endif %}'

        self.helper = FormHelper()
        self.helper.layout = Layout(
            HTML(cancel_btn),
            HTML(submit_btn),
            HTML(prereqs_btn),
            HTML(questions_btn),
            Div(
                'name',
                'xp',
                'xp_can_be_entered_by_students',
                'published',
                'verification_required',
                'icon',
                'short_description',
                'instructions',
                'submission_details',
                'instructor_notes',
                'campaign',
                'common_data',
                'max_repeats',
                'hours_between_repeats',
                'tags',
                'quick_reply',
                Accordion(
                    AccordionGroup(
                        "Basic Prerequisites",
                        # TODO This code should be combined with its use in quest_detail_content.html
                        HTML(
                            "<div class='help-block'><p>If you only want to set a single quest and/or badge as a prerequisite, you can set them here."
                            "{% if object.id %} Note that this will overwrite any current prerequisites that are set. </p><p>{% endif %} "
                            "For more advanced prerequisite options you will need to "
                            "{% if request.user.profile.is_TA %} ask a teacher to set them up for you. "
                            "{% elif not object.id %} save this new quest first."
                            "{% else %}use the <a href='{% url \"quests:quest_prereqs_update\" object.id %}'>Advanced Prerequisites Form</a>."
                            "{% endif %}</p></div>"
                            "<div>Current Prerequisites:</div>"
                            "{% include 'prerequisites/current_prereq_list.html' %}",
                        ),
                        'new_quest_prerequisite',
                        'new_badge_prerequisite',
                        active=False,
                        template='crispy_forms/bootstrap3/accordion-group.html',
                    ),
                    AccordionGroup(
                        "Advanced",
                        'map_transition',
                        'max_xp',
                        'repeat_per_semester',
                        'specific_teacher_to_notify',
                        'blocking',
                        'hideable',
                        'sort_order',
                        'date_available',
                        'time_available',
                        'date_expired',
                        'time_expired',
                        'available_outside_course',
                        'editor',
                        active=False,
                        template='crispy_forms/bootstrap3/accordion-group.html',
                    ),
                ),
                HTML(cancel_btn),
                HTML(submit_btn),
                style="margin-top: 10px;"
            )
        )

    def clean(self):
        cleaned_data = super().clean()

        # make sure blocking quests are not hideable
        blocking = cleaned_data.get('blocking')
        hideable = cleaned_data.get('hideable')

        if blocking and hideable:
            # both fields are valid so far and are True
            raise ValidationError(
                "Blocking quests cannot be Hideable.  In the Advanced section "
                "either turn Hidable off or turn Blocking off."
            )

        # make sure repeat_per_semester isn't combined with unlimited repeats (issue #1531):
        # unlimited repeats never run out, so a per-semester reset would do nothing, and the
        # combination made the quest never repeatable, causing 404s for returning students.
        max_repeats = cleaned_data.get('max_repeats')
        repeat_per_semester = cleaned_data.get('repeat_per_semester')

        if max_repeats == -1 and repeat_per_semester:
            raise ValidationError(
                "A quest with unlimited repeats (Max Repeats = -1) cannot also use "
                "'Repeat per semester', because unlimited repeats never run out and a "
                "new semester would have nothing to reset. Either set Max Repeats to "
                "the number of repeats allowed each semester, or turn off 'Repeat per "
                "semester' (in the Advanced section) to keep unlimited repeats."
            )


class TAQuestForm(QuestForm):
    """QuestForm for a student TA, with the fields a TA may not set left off the form entirely.

    Those fields (``TA_RESTRICTED_QUEST_FIELDS``) are not bound, so a hand-made POST cannot
    reach them: an unbound field is one a ``ModelForm`` never writes to its instance. Editing
    therefore leaves whatever the teacher set in place, and creating falls back to the model
    defaults. ``QuestFormViewMixin.form_valid`` still forces ``published`` and ``editor`` for a
    TA, which keeps a TA's quest a draft of their own no matter which form or view saved it.
    """

    class Meta(QuestForm.Meta):
        fields = tuple(f for f in QuestForm.Meta.fields if f not in TA_RESTRICTED_QUEST_FIELDS)

    def __init__(self, *args, **kwargs):
        """Build the TA form, then drop the restricted fields from the inherited layout.

        Args:
            *args: positional arguments passed through to ``QuestForm``.
            **kwargs: keyword arguments passed through to ``QuestForm``.
        """
        super().__init__(*args, **kwargs)
        # QuestForm's layout names fields this form doesn't have, so take them back out
        remove_layout_fields(self.helper.layout, TA_RESTRICTED_QUEST_FIELDS)


class SanitizeCommentTextMixin:
    """Sanitizes HTML entered in a form's `comment_text` field.

    Comment text is written by anyone, including students, and is rendered with |safe,
    so it must be sanitized or an injected script runs for whoever reads the comment
    (issue #1343). It carries rich HTML from the Summernote editor, so the sanitizer is
    an allow-list rather than a blanket escape: legitimate formatting survives while
    scripts and event-handler attributes do not (issue #2113).

    Every form with a `comment_text` field needs this, the Summernote-backed ones
    included. The Summernote "Safe" widget bleaches on its way in but allows every
    attribute (see `ByteDeckSummernoteSafeInplaceWidget.value_from_datadict`), so it
    stops a `<script>` tag and not an `onerror=`.
    """

    def clean_comment_text(self):
        """Return the submitted ``comment_text`` sanitized to safe HTML for storage/display."""
        return sanitize_comment_html(self.cleaned_data.get('comment_text', ''))


class SubmissionForm(XPCourseChoiceMixin, SanitizeCommentTextMixin, forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=ByteDeckSummernoteSafeInplaceWidget())

    # label, help text, widget and choices all come from XPCourseChoiceMixin, so the question
    # is worded the same here as it is when a teacher grants a badge
    course = forms.ModelChoiceField(queryset=Course.objects.none(), required=False)

    attachments = RestrictedMultiFileFormField(
        required=False,
        max_upload_size=16777216,
        label="Attach files",
        help_text="Hold <kbd>Ctrl</kbd> to select multiple files, 16MB limit per file"
    )


class SubmissionFormCustomXP(SubmissionForm):
    xp_requested = forms.IntegerField(
        label="Requested XP",
        required=True,
        help_text="You need to request an XP value for this submission."
    )

    def __init__(self, *args, **kwargs):
        minimum_xp = kwargs.pop('minimum_xp', 0)
        super().__init__(*args, **kwargs)
        self.fields['xp_requested'].widget.attrs['min'] = minimum_xp


class SubmissionFormStaff(SubmissionForm):
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    awards = forms.ModelMultipleChoiceField(queryset=None, label='Grant Awards', required=False)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.fields['awards'].queryset = Badge.objects.all_manually_granted()
        self.fields['awards'].widget = BadgeSelect2MultipleWidget(
            model=Badge,
            queryset=Badge.objects.all_manually_granted(),
            search_fields=[
                'name__icontains',
            ],
            attrs={'data-theme': 'bootstrap'}
        )


class SubmissionReplyForm(SanitizeCommentTextMixin, forms.Form):
    comment_text = forms.CharField(label='Reply', widget=forms.Textarea(attrs={'rows': 2}))


class BadgeModelChoiceField(BadgeLabel, forms.ModelChoiceField):
    pass


class SubmissionQuickReplyForm(SanitizeCommentTextMixin, forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    award = BadgeModelChoiceField(queryset=None, label='Grant an Award', required=False)

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.fields['award'].queryset = Badge.objects.all_manually_granted()


class SubmissionQuickReplyFormStudent(XPCourseChoiceMixin, SanitizeCommentTextMixin, forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=forms.Textarea(attrs={'rows': 2}))

    # label, help text, widget and choices all come from XPCourseChoiceMixin, so the question
    # is worded the same here as it is when a teacher grants a badge
    course = forms.ModelChoiceField(queryset=Course.objects.none(), required=False)


class CommonDataForm(forms.ModelForm):

    class Meta:
        model = CommonData
        fields = "__all__"
        widgets = {
            "instructions": ByteDeckSummernoteSafeInplaceWidget()
        }
