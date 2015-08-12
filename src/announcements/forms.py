from django import forms
from django.db import models

from datetimewidget.widgets import DateTimeWidget, DateWidget, TimeWidget

from .models import Announcement

def make_custom_datetimefield(f):
    formfield = f.formfield()
    dateTimeOptions = {
        #'format': 'dd-mm-yyyy HH:ii P',
        'showMeridian' : True,
        'todayHighlight': True,
        'minuteStep': 15,
        'pickerPosition': 'bottom-left',
        #'minView': '1',
    }

    if isinstance(f, models.DateTimeField):
        formfield.widget = DateTimeWidget(usel10n = True, options = dateTimeOptions, bootstrap_version=3 )
    elif isinstance(f, models.DateField):
        formfield.widget = DateWidget(usel10n = True, options = dateTimeOptions, bootstrap_version=3)
    elif isinstance(f, models.TimeField):
        formfield.widget = TimeWidget(usel10n = True, options = dateTimeOptions, bootstrap_version=3)

    return formfield


class AnnouncementForm(forms.ModelForm):
    formfield_callback = make_custom_datetimefield
    class Meta:
        model = Announcement
        exclude = ['author']

# class ProfileForm(forms.Form):
#     class Meta:
#         model = Profile
#         # fields = ['name','xp']
#         widgets = {
#
#         }
#         fields = '__all__'

# class ProfileUpdateForm(forms.ModelForm):
#     class Meta:
#         model = Profile
#         fields = '__all__'
