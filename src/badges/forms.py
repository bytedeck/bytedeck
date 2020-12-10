from django import forms
from django.contrib.auth.models import User
from django_select2.forms import Select2Widget, ModelSelect2MultipleWidget

from profile_manager.models import Profile
from .models import Badge, BadgeAssertion


class BadgeForm(forms.ModelForm):

    class Meta:
        model = Badge
        fields = '__all__'
        # exclude = None


class BadgeAssertionForm(forms.ModelForm):
    class Meta:
        model = BadgeAssertion
        # fields = '__all__'
        exclude = ['ordinal', 'issued_by', 'semester']
        widgets = {
            'user': Select2Widget(),
            'badge': Select2Widget(),
        }

    def __init__(self, *args, **kwargs):
        super(BadgeAssertionForm, self).__init__(*args, **kwargs)

        self.fields['user'].queryset = User.objects.order_by('profile')
        # It appears that sometimes a profile does not exist causing this to fail and the user field to not appear
        self.fields['user'].label_from_instance = lambda obj: "%s -- %s" % (
            obj.profile if hasattr(obj, 'profile') else "", obj.username)


class BulkBadgeAssertionForm(forms.Form):
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    badge = forms.ModelChoiceField(queryset=None, required=True)
    students = forms.ModelMultipleChoiceField(queryset=None)

    def __init__(self, *args, **kwds):
        super(BulkBadgeAssertionForm, self).__init__(*args, **kwds)
        # Is this still relevant because no longer using djconfig?  Not broken so...
        # Need to set queryset on init because config isn't available until apps are loaded.
        # https://github.com/nitely/django-djconfig/issues/14
        self.fields['students'].queryset = Profile.objects.all_for_active_semester()
        self.fields['badge'].queryset = Badge.objects.all_manually_granted()

        self.fields['students'].widget = ModelSelect2MultipleWidget(
            model=Profile,
            queryset=Profile.objects.all_for_active_semester(),
            search_fields=[
                'first_name__istartswith',
                'last_name__istartswith',
                'preferred_name__istartswith',
                'user__username__istartswith',
            ]
        )
