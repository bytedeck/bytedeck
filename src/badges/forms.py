from django import forms
from django.contrib.auth.models import User
from django.forms.fields import MultipleChoiceField
from django_select2.forms import Select2Widget, Select2MultipleWidget, ModelSelect2Widget, ModelSelect2MultipleWidget

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
            obj.profile if hasattr(obj, 'profile') else "", obj.username
        )


class BulkBadgeAssertionForm(forms.Form):
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    badge = forms.ModelChoiceField(
        queryset=Badge.objects.all(),
        required=True, 
        widget=ModelSelect2Widget(
            model=Badge,
            search_fields=['name__icontains'],
        )
    )
    # students = forms.ModelMultipleChoiceField(queryset=None)
    students = forms.ModelMultipleChoiceField(
        # TODO just use the user objects here instead of profile
        # Goign back to the user just to sort by profile string is...a hack.  How to do that properly?!
        queryset=Profile.objects.all().order_by('user__profile'),
        required=True,
        widget=ModelSelect2MultipleWidget(
            model=Profile,
            search_fields=[
                'first_name__istartswith',
                'last_name__istartswith',
                'preferred_name__istartswith',
                'user__username__istartswith',
            ],
            label_from_instance=lambda obj: "%s -- %s" % (obj, obj.user.username)
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['students'].label_from_instance = lambda obj: "%s -- %s" % (obj, obj.user.username)
