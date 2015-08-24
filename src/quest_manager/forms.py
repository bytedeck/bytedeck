from django import forms
from django.db import models
from django.forms.extras.widgets import SelectDateWidget

from datetimewidget.widgets import DateTimeWidget, DateWidget, TimeWidget
from django_summernote.widgets import SummernoteWidget, SummernoteInplaceWidget

from .models import Quest

def make_custom_datetimefield(f):
    formfield = f.formfield()
    dateTimeOptions = {
        'showMeridian' : False,
        #'todayBtn': True,
        'todayHighlight': True,
        'minuteStep': 5,
        'pickerPosition': 'bottom-left',
    }

    if isinstance(f, models.DateTimeField):
        formfield.widget = DateTimeWidget(usel10n = True, options = dateTimeOptions, bootstrap_version=3 )
    elif isinstance(f, models.DateField):
        formfield.widget = DateWidget(usel10n = True, options = dateTimeOptions, bootstrap_version=3)
        # formfield.widget = SelectDateWidget()
    elif isinstance(f, models.TimeField):
        formfield.widget = TimeWidget(usel10n = True, options = dateTimeOptions, bootstrap_version=3)
    elif isinstance(f, models.TextField):
        formfield.widget = SummernoteWidget()
    return formfield

## Demo of how to create a form without using a model
# class QuestFormCustom(forms.Form):
#     quest = forms.CharField()  # default is required = True
#     xp = forms.IntegerField()
##

class QuestForm(forms.ModelForm):
    formfield_callback = make_custom_datetimefield
    class Meta:
        model = Quest
        fields = '__all__'
        # exclude = None


class SubmissionForm(forms.Form):
    comment_text = forms.CharField(label='Submission', widget=SummernoteWidget())

class SubmissionReplyForm(forms.Form):
    comment_text = forms.CharField(label='Reply', widget=forms.Textarea(attrs={'rows':2}))

class SubmissionQuickReplyForm(forms.Form):
    comment_text = forms.CharField(label='', required=False, widget=forms.Textarea(attrs={'rows':2}))



    # def clean_name(self):
    #     name = self.cleaned_data.get('name')
    #     return name
    #
    # def clean_xp(self):
    #     xp = self.cleaned_data.get('xp')
    #     return xp
