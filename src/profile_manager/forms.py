from django import forms

from .models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['student_number', 'first_name', 'preferred_name', 'preferred_internal_only',
                  'last_name', 'alias', 'avatar', 'grad_year',  
                  'get_notifications_by_email', 'get_announcements_by_email', 
                  'visible_to_other_students', 'dark_theme', 'silent_mode', 'custom_stylesheet']

    def __init__(self, *args, **kwargs):
        super(ProfileForm, self).__init__(*args, **kwargs)
        self.fields['grad_year'] = forms.ChoiceField(
            choices=Profile.get_grad_year_choices()
        )

    # UNIQUE if NOT NULL
    def clean_alias(self):
        return self.cleaned_data['alias'] or None
