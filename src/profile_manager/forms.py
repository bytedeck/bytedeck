from django import forms

from .models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['student_number', 'first_name', 'preferred_name', 'last_name', 'alias',
                  'grad_year', 'avatar', 'visible_to_other_students', 'dark_theme']

    # UNIQUE if NOT NULL
    def clean_alias(self):
        return self.cleaned_data['alias'] or None
