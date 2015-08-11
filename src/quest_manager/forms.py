from django import forms
from django.db import models
from .models import Quest

from datetimewidget.widgets import DateTimeWidget, DateWidget, TimeWidget
#from django_summernote.widgets import SummernoteWidget, SummernoteInplaceWidget

## Us datepickers for all forms
## http://strattonbrazil.blogspot.ca/2011/03/using-jquery-uis-date-picker-on-all.html
# def make_custom_datefield(f):
#     formfield = f.formfield()
#     if isinstance(f, models.DateField):
#         formfield.widget.format = '%m/%d/%Y'
#         formfield.widget.attrs.update({'class':'datePicker',
#                                         'readonly':'true',
#                                         })
#     return formfield

def make_custom_datetimefield(f):
    formfield = f.formfield()
    dateTimeOptions = {
        'showMeridian' : True,
        'todayHighlight': True,
        'minuteStep': 15,
        'pickerPosition': 'bottom-left',
    }

    if isinstance(f, models.DateTimeField):
        formfield.widget = DateTimeWidget(usel10n = True, options = dateTimeOptions, bootstrap_version=3 )
    elif isinstance(f, models.DateField):
        formfield.widget = DateWidget(usel10n = True, bootstrap_version=3)
    elif isinstance(f, models.TimeField):
        formfield.widget = DateWidget(usel10n = True, bootstrap_version=3)

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


    # def clean_name(self):
    #     name = self.cleaned_data.get('name')
    #     return name
    #
    # def clean_xp(self):
    #     xp = self.cleaned_data.get('xp')
    #     return xp
