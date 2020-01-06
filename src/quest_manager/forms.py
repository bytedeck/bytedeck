from bootstrap_datepicker_plus import DatePickerInput, TimePickerInput
from django import forms
from django_select2.forms import ModelSelect2MultipleWidget
from django_summernote.widgets import SummernoteInplaceWidget

from badges.models import Badge
from utilities.fields import RestrictedFileFormField
from .models import Quest


class QuestForm(forms.ModelForm):

    class Meta:
        model = Quest
        fields = ('name', 'visible_to_students', 'xp', 'icon', 'short_description',
                  'verification_required', 'instructions',
                  'campaign', 'common_data', 'submission_details', 'instructor_notes',
                  'max_repeats', 'hours_between_repeats',
                  'specific_teacher_to_notify',
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
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super(QuestForm, self).__init__(*args, **kwargs)

        # Don't let TA's make quests visible to students.  Teachers can do this when they approve a TA's draft quest
        if user.profile.is_TA:
            self.fields['visible_to_students'].widget = forms.HiddenInput()
            # self.fields['max_repeats'].widget = forms.HiddenInput()
            # self.fields['hours_between_repeats'].widget = forms.HiddenInput()
            # self.fields['specific_teacher_to_notify'].widget = forms.HiddenInput()
            # self.fields['hideable'].widget = forms.HiddenInput()
            # self.fields['sort_order'].widget = forms.HiddenInput()
            # self.fields['date_available'].widget = forms.HiddenInput()
            # self.fields['time_available'].widget = forms.HiddenInput()
            # self.fields['date_expired'].widget = forms.HiddenInput()
            # self.fields['time_expired'].widget = forms.HiddenInput()
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


class BadgeLabel:
    def label_from_instance(self, obj):
        return "{} ({} XP)".format(str(obj), obj.xp)


class BadgeSelect2MultipleWidget(BadgeLabel, ModelSelect2MultipleWidget):
    pass


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
