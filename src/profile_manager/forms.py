from django import forms

from django.contrib.auth import get_user_model

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
        super().__init__(*args, **kwargs)

        self.fields['grad_year'] = forms.ChoiceField(
            choices=Profile.get_grad_year_choices()
        )
        
        self.fields['email'].initial = self.instance.user.email

    # UNIQUE if NOT NULL
    def clean_alias(self):
        return self.cleaned_data['alias'] or None

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        user = self.instance.user
        user.email = self.cleaned_data['email']
        user.save()

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
        user_fields = list(set(self._meta.fields) & set([field.name for field in user._meta.fields]))
        for name in user_fields:
            user.__dict__[name] = self.cleaned_data[name]
        user.save(update_fields=user_fields)

        # Use updated profile instance to save profile model
        profile = self.instance.profile
        profile.is_TA = self.cleaned_data['is_TA']
        profile.save(update_fields=['is_TA'])

        return self.instance
