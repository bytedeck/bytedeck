from django import forms
from django.contrib.auth.models import User
from django_select2.forms import Select2Widget, ModelSelect2Widget, ModelSelect2MultipleWidget

from courses.forms import XPCourseChoiceMixin
from courses.models import CourseStudent
from profile_manager.models import Profile
from tags.forms import BootstrapTaggitSelect2Widget
from utilities.fa_icon_widget import FontAwesomeAdminFormMixin, FontAwesomeIconPickerWidget
from .models import Badge, BadgeAssertion, BadgeRarity, BadgeType


class BadgeForm(forms.ModelForm):

    class Meta:
        model = Badge
        fields = (
            'name', 'xp', 'icon', 'short_description', 'badge_type', 'tags',
            'sort_order', 'published', 'map_transition', 'import_id'
        )

        widgets = {
            'tags': BootstrapTaggitSelect2Widget(attrs={'data-theme': 'bootstrap'})
        }


class BadgeAssertionForm(XPCourseChoiceMixin, forms.ModelForm):
    """Grant one badge to one student, saying which of their courses its XP counts toward.

    The course question only appears when this student has more than one course and the deck
    asks about it at all, matching what students see when they hand in a quest (issue #2440).
    It also needs the student to be known already, which they are when granting from someone's
    profile; on the open grant page the student is picked on this same form, so there is nobody
    to look courses up for and the badge is shared between their courses.
    """

    split_evenly_label = "Split evenly between the student's courses"

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

    def clean(self):
        """Refuse a course that is not one of the student being granted the badge.

        The course choices are built for the student named in the URL, while the student who
        actually receives the badge comes from this form's own user field, so a posted pair
        that does not match would attach a course the recipient is not registered in.

        Returns:
            dict: the cleaned data, with a 'course' error when the two do not match.
        """
        cleaned_data = super().clean()
        course = cleaned_data.get('course')
        user = cleaned_data.get('user')
        if course and user and not CourseStudent.objects.current_courses(user).filter(course=course).exists():
            self.add_error('course', f'{user} is not registered in {course}.')
        return cleaned_data


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
        queryset=Profile.objects.all().order_by('user__first_name', 'user__last_name'),
        required=True,
        widget=ProfileMultiSelectWidget(attrs={'data-theme': 'bootstrap'}),
    )


class BadgeTypeForm(forms.ModelForm):
    """Badge type add/edit form.

    The Font Awesome icon field uses the searchable icon picker
    (:class:`utilities.fa_icon_widget.FontAwesomeIconPickerWidget`), the same one the
    rank form uses, so a teacher can browse the icon set instead of having to know a
    name by heart.
    """

    class Meta:
        """Binds the icon picker and a plain-language label onto the badge type's icon field."""

        model = BadgeType
        fields = ('name', 'sort_order', 'fa_icon')
        widgets = {
            'fa_icon': FontAwesomeIconPickerWidget(),
        }
        labels = {
            # "Fa icon" is jargon; call it what it is.
            'fa_icon': 'Icon',
        }


class BadgeRarityForm(FontAwesomeAdminFormMixin, forms.ModelForm):
    """Badge rarity add/edit form for the Django admin, which is the only place
    rarities are edited.

    Same icon picker as the site's icon forms, plus the stylesheets the admin does not
    load on its own (see :class:`utilities.fa_icon_widget.FontAwesomeAdminFormMixin`).
    """

    class Meta:
        """Binds the icon picker and a plain-language label onto the rarity's icon field."""

        model = BadgeRarity
        fields = '__all__'
        widgets = {
            'fa_icon': FontAwesomeIconPickerWidget(),
        }
        labels = {
            'fa_icon': 'Icon',
        }
