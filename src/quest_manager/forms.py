from django import forms
from django.db import models
from .models import Quest

## Us datepickers for all forms
## http://strattonbrazil.blogspot.ca/2011/03/using-jquery-uis-date-picker-on-all.html
def make_custom_datefield(f):
    formfield = f.formfield()
    if isinstance(f, models.DateField):
        formfield.widget.format = '%m/%d/%Y'
        formfield.widget.attrs.update({'class':'datePicker',
                                        'readonly':'true',
                                        })
    return formfield



## Demo of how to create a form without using a model
class QuestFormCustom(forms.Form):
    quest = forms.CharField()  # default is required = True
    xp = forms.IntegerField()
##

class NewQuestForm(forms.ModelForm):
    formfield_callback = make_custom_datefield
    class Meta:
        model = Quest
        # fields = ['name','xp']
        fields = '__all__'


    # def clean_name(self):
    #     name = self.cleaned_data.get('name')
    #     return name
    #
    # def clean_xp(self):
    #     xp = self.cleaned_data.get('xp')
    #     return xp
