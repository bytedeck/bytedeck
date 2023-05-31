from django import forms
from django.contrib.auth.models import User
from django_select2.forms import Select2Widget, ModelSelect2Widget, ModelSelect2MultipleWidget

from profile_manager.models import Profile
from siteconfig.models import SiteConfig
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
            'tags': BootstrapTaggitSelect2Widget()
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['badge_type'].label = f"{SiteConfig.get().custom_name_for_badge} type"
        self.fields['map_transition'].help_text = f"Break maps at this {SiteConfig.get().custom_name_for_badge.lower()}. This \
            {SiteConfig.get().custom_name_for_badge.lower()} will link to a new map."
        self.fields['import_id'].help_text = f"Only edit this if you want to link to a {SiteConfig.get().custom_name_for_badge.lower()} in another \
            system so that when importing from that other system, it will update this {SiteConfig.get().custom_name_for_badge.lower()} too. \
            Otherwise do not edit this or it will break existing links!"


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
        super().__init__(*args, **kwargs)

        self.fields['user'].queryset = User.objects.order_by('profile')
        # It appears that sometimes a profile does not exist causing this to fail and the user field to not appear
        self.fields['user'].label_from_instance = lambda obj: "{} | {}".format(
            obj.profile if hasattr(obj, 'profile') else "", obj.username
        )


class ProfileMultiSelectWidget(ModelSelect2MultipleWidget):
    model = Profile
    search_fields = [
        'first_name__istartswith',
        'last_name__istartswith',
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
        )
    )
    # students = forms.ModelMultipleChoiceField(queryset=None)
    students = forms.ModelMultipleChoiceField(
        # TODO just use the user objects here instead of profile
        # Goign back to the user just to sort by profile string is...a hack.  How to do that properly?!
        queryset=Profile.objects.all().order_by('user__profile'),
        required=True,
        widget=ProfileMultiSelectWidget(),
    )
