from django import forms

from django.contrib.auth import get_user_model
from django.urls import reverse

from allauth.utils import email_address_exists

from .models import Profile


class ProfileForm(forms.ModelForm):

    # this will be saved in User model
    email = forms.EmailField(required=False)

    class Meta:
        model = Profile
        fields = ['preferred_name', 'preferred_internal_only',
                  'alias', 'avatar', 'grad_year', 'email',
                  'get_announcements_by_email', 'get_notifications_by_email',
                  'visible_to_other_students', 'dark_theme', 'silent_mode', 'custom_stylesheet']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)

        super().__init__(*args, **kwargs)

        self.fields['grad_year'] = forms.ChoiceField(
            choices=Profile.get_grad_year_choices()
        )

        self.fields['email'].initial = self.instance.user.email

        user = self.instance.user

        # It is possible that the user registered without an email so instead of using
        # user.emailaddress_set.get(...), let's just use .first() since it would return
        # None instead of raising a DoesNotExist error
        email_address = user.emailaddress_set.filter(email=user.email).first()

        if (user.email and email_address is None) or (email_address and email_address.verified is False):
            resend_email_url = reverse('profiles:profile_resend_email_verification', args=[self.instance.pk])
            self.fields['email'].help_text = (
                '<i class="fa fa-ban text-danger" aria-hidden="true"></i> Not yet verified. '
                f'<a href="{resend_email_url}">Re-send verification link</a>'
            )

        if email_address and email_address.verified:
            self.fields['email'].help_text = '<i class="fa fa-check text-success" aria-hidden="true"></i>&nbsp;Verified'

    # UNIQUE if NOT NULL
    def clean_alias(self):
        return self.cleaned_data['alias'] or None

    def clean_email(self):
        email = self.cleaned_data['email']

        if email and email_address_exists(email, exclude_user=self.instance.user):
            raise forms.ValidationError("A user is already registered with this email address")

        return email

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        user = self.instance.user

        modified_email = user.email != self.cleaned_data['email']
        if modified_email:
            user.email = self.cleaned_data['email']
            user.save()

        from allauth.account.utils import send_email_confirmation
        if self.request and modified_email:
            send_email_confirmation(
                request=self.request,
                user=user,
                signup=False,
                email=user.email,
            )

        return self.instance


class UserForm(forms.ModelForm):
    """
        Staff only form for profile update view
    """

    is_TA = forms.BooleanField(required=False)

    class Meta:
        model = get_user_model()
        fields = [
            'username', 'first_name', 'last_name', 'is_TA', 'is_staff', 'is_active',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__cached_username = self.instance.username

        self.fields['username'].help_text = (
            'WARNING: If you change this user\'s username they will no longer be able to log in with their old username.'
            'Make sure to inform the user of their new username!'
        )

        self.fields['is_TA'].label = 'TA'
        self.fields['is_TA'].initial = self.instance.profile.is_TA
        self.fields['is_TA'].help_text = Profile._meta.get_field('is_TA').help_text

    def save(self):
        # update self.instance since ProfileForm changes User model vars
        # super().save() not saving email correctly so we only update the model fields in UserForm.fields
        # This code only updates the UserModel fields that is in self._meta.fields
        # required since Userform saves over user.email field which is also a field saved in ProfileForm.
        # This prevents email field from being overwritten in Userform
        user = self.instance
        user_fields = list(set(self._meta.fields) & {field.name for field in user._meta.fields})
        for name in user_fields:
            user.__dict__[name] = self.cleaned_data[name]

        user.save(update_fields=user_fields)

        # Use updated profile instance to save profile model
        profile = self.instance.profile
        profile.is_TA = self.cleaned_data['is_TA']
        profile.save(update_fields=['is_TA'])

        return self.instance
