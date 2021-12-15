from django import forms

from .models import Profile


class ProfileForm(forms.ModelForm):

    # this will be saved in User.email
    email = forms.EmailField(required=False)

    class Meta:
        model = Profile
        fields = ['preferred_name', 'preferred_internal_only',
                  'alias', 'avatar', 'grad_year', 'email',
                  'get_announcements_by_email', 'get_notifications_by_email',
                  'visible_to_other_students', 'dark_theme', 'silent_mode', 'custom_stylesheet']

    def __init__(self, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        self.fields['grad_year'] = forms.ChoiceField(
            choices=Profile.get_grad_year_choices()
        )
        self.fields['email'].initial = self.instance.user.email

    # UNIQUE if NOT NULL
    def clean_alias(self):
        return self.cleaned_data['alias'] or None

    def save(self, *args, **kwargs):
        super(ProfileForm, self).save(*args, **kwargs)
        user = self.instance.user
        user.email = self.cleaned_data['email']
        user.save()

        return self.instance
