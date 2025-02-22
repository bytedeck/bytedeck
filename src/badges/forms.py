from django import forms
from django.contrib.auth.models import User
from django_select2.forms import Select2Widget, ModelSelect2Widget, ModelSelect2MultipleWidget

from profile_manager.models import Profile
from tags.forms import BootstrapTaggitSelect2Widget
from .models import Badge, BadgeAssertion


class BadgeForm(forms.ModelForm):

    class Meta:
        model = Badge
        fields = (
            'name', 'xp', 'icon', 'short_description', 'badge_type', 'tags',
            'sort_order', 'active', 'map_transition', 'import_id'
        )

        widgets = {
            'tags': BootstrapTaggitSelect2Widget(attrs={'data-theme': 'bootstrap'})
        }


class BadgeAssertionForm(forms.ModelForm):
    class Meta:
        model = BadgeAssertion
        # fields = '__all__'
        exclude = ['ordinal', 'issued_by', 'semester']
        widgets = {
            'user': Select2Widget(attrs={'data-theme': 'bootstrap'}),
            'badge': Select2Widget(attrs={'data-theme': 'bootstrap'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['user'].queryset = User.objects.order_by('profile')
        # It appears that sometimes a profile does not exist causing this to fail and the user field to not appear
        self.fields['user'].label_from_instance = lambda obj: "{} | {}".format(
            obj.profile if hasattr(obj, 'profile') else "", obj.username
        )


class ProfileMultiSelectWidget(ModelSelect2MultipleWidget):
    model = Profile
    search_fields = [
        'user__first_name__istartswith',
        'user__last_name__istartswith',
        'preferred_name__istartswith',
        'user__username__istartswith',
    ]

    def label_from_instance(self, obj):
        return f"{obj} | {obj.user.username}"


class BulkBadgeAssertionForm(forms.Form):
    # Queryset needs to be set on creation in __init__(), otherwise bad stuff happens upon initial migration
    badge = forms.ModelChoiceField(
        queryset=Badge.objects.all(),
        required=True,
        widget=ModelSelect2Widget(
            model=Badge,
            search_fields=['name__icontains'],
            attrs={'data-theme': 'bootstrap'}
        )
    )
    students = forms.ModelMultipleChoiceField(
        # TODO just use the user objects here instead of profile
        # Goign back to the user just to sort by profile string is...a hack.  How to do that properly?!
        queryset=Profile.objects.select_related('user').order_by('user__first_name', 'user__last_name'),
        required=True,
        widget=ProfileMultiSelectWidget(attrs={'data-theme': 'bootstrap'}),
    )
