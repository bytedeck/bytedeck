from django_select2.forms import Select2Widget, ModelSelect2Widget
from datetime import date

from bootstrap_datepicker_plus import DatePickerInput, TimePickerInput
from crispy_forms.bootstrap import Accordion, AccordionGroup
from crispy_forms.helper import FormHelper
from crispy_forms.layout import HTML, Div, Layout
from django import forms
from django_select2.forms import ModelSelect2MultipleWidget
from django_summernote.widgets import SummernoteInplaceWidget
from utilities.fields import RestrictedFileFormField

from badges.models import Badge
from .models import Quest


class BadgeLabel:
    def label_from_instance(self, obj):
        return "{} ({} XP)".format(str(obj), obj.xp)


class BadgeSelect2MultipleWidget(BadgeLabel, ModelSelect2MultipleWidget):
    pass


class QuestForm(forms.ModelForm):

    new_quest_prerequisite = forms.ModelChoiceField(
        # to_field_name="name",
        required=False,
        queryset=Quest.objects.all(),
        widget=ModelSelect2Widget(
            model=Quest,
            search_fields=['name__icontains'],
        ),
    )

    new_badge_prerequisite = forms.ModelChoiceField(
        widget=ModelSelect2Widget(
            model=Badge,
            search_fields=['name__icontains'],
        ),
        queryset=Badge.objects.all(),
        # to_field_name="name",
        required=False,
    )

    class Meta:
        model = Quest
        fields = ('name', 'visible_to_students', 'xp', 'icon', 'short_description',
                  'verification_required', 'instructions',
                  'campaign', 'common_data', 'submission_details', 'instructor_notes',
                  'repeat_per_semester', 'max_repeats', 'hours_between_repeats',
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
            'instructions': SummernoteInplaceWidget(),
            'submission_details': SummernoteInplaceWidget(),
            'instructor_notes': SummernoteInplaceWidget(),

            'date_available': DatePickerInput(format='%Y-%m-%d'),

            'time_available': TimePickerInput(),
            'date_expired': DatePickerInput(format='%Y-%m-%d'),
            'time_expired': TimePickerInput(),
            'campaign': Select2Widget(),
            'common_data': Select2Widget(),
            'specific_teacher_to_notify': Select2Widget()
        }

    def __init__(self, *args, **kwargs):
        super(QuestForm, self).__init__(*args, **kwargs)

        self.fields['date_available'].initial = date.today().strftime('%Y-%m-%d'),

        cancel_btn = '<a href="{{ cancel_url }}" role="button" class="btn btn-danger">Cancel</a> '
        submit_btn = '<input type="submit" value="{{ submit_btn_value }}" class="btn btn-success"/> '
        admin_btn = (
            '<a href="/admin/quest_manager/quest/{{object.id}}"'
            ' title="This is required to edit prerequisites"'
            ' role="button" class="btn btn-default">'
            ' via Admin</a>'
        )

        self.helper = FormHelper()
        self.helper.layout = Layout(
            HTML(cancel_btn),
            HTML(submit_btn),
            HTML(admin_btn),
            Div(
                'name',
                'xp',
                'visible_to_students',
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
                Accordion(
                    AccordionGroup(
                        "Basic Prerequisites",
                        # TODO This code should be combined with its use in quest_detail_content.html
                        HTML(
                            "<div class='help-block'>If you only want to set a single quest and/or badge as a prerequisite, you can set them here. "
                            "Note that this will overwrite any current prerequisites that are set. For more interesting prerequisite options you "
                            " will need to edit the quest via the <a href='/admin/quest_manager/quest/{{object.id}}'>Admin form</a>.</div>"
                            "<div>Current Prerequisites</div>"
                            "<div><ul class='left-aligned'><small>"
                            "{% for p in form.instance.prereqs %}"
                            "<li><a href='{{ p.get_prereq.get_absolute_url }}'>{{ p }}</a></li>"
                            "{% empty %}<li>None</li>"
                            "{% endfor %}</small></ul></div>",
                        ),
                        'new_quest_prerequisite',
                        'new_badge_prerequisite',
                        active=False,
                        template='crispy_forms/bootstrap3/accordion-group.html',
                    ),
                    AccordionGroup(
                        "Advanced",
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
                        'archived',
                        'editor',
                        active=False,
                        template='crispy_forms/bootstrap3/accordion-group.html',
                    ),
                ),
                HTML(cancel_btn),
                HTML(submit_btn),
                HTML(admin_btn),
                style="margin-top: 10px;"
            )
        )


class TAQuestForm(QuestForm):
    """ Modified QuestForm that removes some fields TAs should not be able to set. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # SET visible to students here to?
        self.fields['visible_to_students'].widget = forms.HiddenInput()
        self.fields['available_outside_course'].widget = forms.HiddenInput()
        self.fields['archived'].widget = forms.HiddenInput()
        self.fields['editor'].widget = forms.HiddenInput()


class SubmissionForm(forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=SummernoteInplaceWidget())

    attachments = RestrictedFileFormField(required=False,
                                          max_upload_size=16777216,
                                          widget=forms.ClearableFileInput(attrs={'multiple': True}),
                                          label="Attach files",
                                          help_text="Hold Ctrl to select multiple files, 16MB limit per file")


class SubmissionFormStaff(SubmissionForm):
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    awards = forms.ModelMultipleChoiceField(queryset=None, label='Grant Awards', required=False)

    def __init__(self, *args, **kwds):
        super(SubmissionFormStaff, self).__init__(*args, **kwds)

        self.fields['awards'].queryset = Badge.objects.all_manually_granted()
        self.fields['awards'].widget = BadgeSelect2MultipleWidget(
            model=Badge,
            queryset=Badge.objects.all_manually_granted(),
            search_fields=[
                'name__icontains',
            ]
        )


class SubmissionReplyForm(forms.Form):
    comment_text = forms.CharField(label='Reply', widget=forms.Textarea(attrs={'rows': 2}))


class BadgeModelChoiceField(BadgeLabel, forms.ModelChoiceField):
    pass


class SubmissionQuickReplyForm(forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    award = BadgeModelChoiceField(queryset=None, label='Grant an Award', required=False)

    def __init__(self, *args, **kwds):
        super(SubmissionQuickReplyForm, self).__init__(*args, **kwds)
        self.fields['award'].queryset = Badge.objects.all_manually_granted()
