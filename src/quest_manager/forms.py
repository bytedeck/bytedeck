from badges.models import Badge

from datetimewidget.widgets import DateTimeWidget, DateWidget, TimeWidget
from django import forms
from django.db import models
from django_summernote.widgets import SummernoteWidget
from .formatChecker import MultiFileField
from .models import Quest


def make_custom_datetimefield(f):
    formfield = f.formfield()
    date_time_options = {
        'showMeridian': False,
        # 'todayBtn': True,
        'todayHighlight': True,
        'minuteStep': 5,
        'pickerPosition': 'bottom-left',
    }

    if isinstance(f, models.DateTimeField):
        formfield.widget = DateTimeWidget(usel10n=True, options=date_time_options, bootstrap_version=3)
    elif isinstance(f, models.DateField):
        formfield.widget = DateWidget(usel10n=True, options=date_time_options, bootstrap_version=3)
        # formfield.widget = SelectDateWidget()
    elif isinstance(f, models.TimeField):
        formfield.widget = TimeWidget(usel10n=True, options=date_time_options, bootstrap_version=3)
    elif isinstance(f, models.TextField):
        formfield.widget = SummernoteWidget()
    return formfield


# Demo of how to create a form without using a model
# class QuestFormCustom(forms.Form):
#     quest = forms.CharField()  # default is required = True
#     xp = forms.IntegerField()

class QuestForm(forms.ModelForm):
    formfield_callback = make_custom_datetimefield

    class Meta:
        model = Quest
        fields = ('name', 'visible_to_students', 'xp', 'icon', 'short_description',
                  'verification_required', 'instructions',
                  'campaign', 'common_data', 'submission_details', 'instructor_notes',
                  'max_repeats', 'hours_between_repeats',
                  'specific_teacher_to_notify',
                  'hideable', 'sort_order', 'date_available', 'time_available', 'date_expired', 'time_expired',
                  'available_outside_course', 'archived', 'editor')

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


class QuestFormTA(QuestForm):
    def __init__(self, request, *args, **kwargs):
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
        # self.fields['available_outside_course'].widget = forms.HiddenInput()
        self.fields['archived'].widget = forms.HiddenInput()


class SubmissionForm(forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=SummernoteWidget())
    # docfile = forms.FileField(label='Add a file to your submission',
    #                                     required=False)
    # docfile = RestrictedFileField(label='Add a file to your submission (16MB limit)',
    #                                     required=False,
    #                                     max_upload_size=16777216 )
    files = MultiFileField(max_num=5, min_num=0, maximum_file_size=1024 * 1024 * 16,
                           label='Add files (hold Ctrl to select up to 5 files, 16MB limit per file)',
                           required=False
                           )


class SubmissionFormStaff(SubmissionForm):
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    award = forms.ModelChoiceField(queryset=None, label='Grant an Award', required=False)

    def __init__(self, *args, **kwds):
        super(SubmissionFormStaff, self).__init__(*args, **kwds)

        self.fields['award'].queryset = Badge.objects.all_manually_granted()


class SubmissionReplyForm(forms.Form):
    comment_text = forms.CharField(label='Reply', widget=forms.Textarea(attrs={'rows': 2}))


class SubmissionQuickReplyForm(forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    award = forms.ModelChoiceField(queryset=None, label='Grant an Award', required=False)

    def __init__(self, *args, **kwds):
        super(SubmissionQuickReplyForm, self).__init__(*args, **kwds)
        self.fields['award'].queryset = Badge.objects.all_manually_granted()
