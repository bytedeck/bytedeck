from django import forms
from django.contrib.auth.models import User
from django.db import models
from django.forms.extras.widgets import SelectDateWidget

from datetimewidget.widgets import DateTimeWidget, DateWidget, TimeWidget


from .models import Badge, BadgeAssertion

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

    return formfield

class BadgeForm(forms.ModelForm):
    formfield_callback = make_custom_datetimefield
    class Meta:
        model = Badge
        fields = '__all__'
        # exclude = None

class BadgeAssertionForm(forms.ModelForm):
    class Meta:
        model = BadgeAssertion
        # fields = '__all__'
        exclude = ['ordinal', 'issued_by', 'semester']

    def __init__(self, *args, **kwds):
        super(BadgeAssertionForm, self).__init__(*args, **kwds)
        self.fields['user'].queryset = User.objects.order_by('profile__first_name', 'username')
        self.fields['user'].label_from_instance = lambda obj: "%s (%s)" % (obj.profile, obj.username)
