from datetimewidget.widgets import DateTimeWidget, DateWidget, TimeWidget
from django import forms
from django.contrib.auth.models import User
from django.db import models
from django_select2.forms import ModelSelect2MultipleWidget

from profile_manager.models import Profile
from .models import Badge, BadgeAssertion


def make_custom_datetimefield(f):
    formfield = f.formfield()
    dateTimeOptions = {
        'showMeridian': False,
        # 'todayBtn': True,
        'todayHighlight': True,
        'minuteStep': 5,
        'pickerPosition': 'bottom-left',
    }

    if isinstance(f, models.DateTimeField):
        formfield.widget = DateTimeWidget(usel10n=True, options=dateTimeOptions, bootstrap_version=3)
    elif isinstance(f, models.DateField):
        formfield.widget = DateWidget(usel10n=True, options=dateTimeOptions, bootstrap_version=3)
        # formfield.widget = SelectDateWidget()
    elif isinstance(f, models.TimeField):
        formfield.widget = TimeWidget(usel10n=True, options=dateTimeOptions, bootstrap_version=3)

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

    def __init__(self, *args, **kwargs):
        super(BadgeAssertionForm, self).__init__(*args, **kwargs)

        self.fields['user'].queryset = User.objects.order_by('profile__first_name', 'username')
        #self.fields['user'].queryset = User.objects.order_by('username')
        self.fields['user'].label_from_instance = lambda obj: "%s (%s)" % (str(obj.profile), obj.username)


class StudentsCustomTitleWidget(ModelSelect2MultipleWidget):
    model = Profile
    # queryset = Profile.objects.all()
    search_fields = [
        'first_name__istartswith',
        'last_name__istartswith',
        'preferred_name__istartswith',
    ]
    # queryset = Profile.objects.all_for_active_semester()

    # SHOULD BE USING USER NOT PROFILE!
    # model = User
    # search_fields = [
    #     'first_name__istartswith',
    #     'last_name__istartswith',
    #     'username__istartswith',
    # ]
    #
    # def label_from_instance(self, obj):
    #     return obj.get_full_name().upper()



class BulkBadgeAssertionForm(forms.Form):
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    badge = forms.ModelChoiceField(queryset=None, required=True)
    students = forms.ModelMultipleChoiceField(queryset=None, widget=StudentsCustomTitleWidget())

    def __init__(self, *args, **kwds):
        super(BulkBadgeAssertionForm, self).__init__(*args, **kwds)
        # Need to set queryset on init because config isn't available until apps are loaded.
        # https://github.com/nitely/django-djconfig/issues/14
        self.fields['students'].queryset = Profile.objects.all_for_active_semester()
        self.fields['badge'].queryset = Badge.objects.all_manually_granted()
