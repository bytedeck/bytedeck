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
        fields = '__all__'
        # exclude = None


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
    awards = Badge.objects.all()
    awards = Badge.objects.all_manually_granted()
    award = forms.ModelChoiceField(queryset=awards, label='Grant an Award', required=False)


class SubmissionReplyForm(forms.Form):
    comment_text = forms.CharField(label='Reply', widget=forms.Textarea(attrs={'rows': 2}))


class SubmissionQuickReplyForm(forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=forms.Textarea(attrs={'rows': 2}))
    # awards = Badge.objects.all()
    awards = Badge.objects.all_manually_granted()
    award = forms.ModelChoiceField(queryset=awards, label='Grant an Award', required=False)
