from django import forms

from .models import Profile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        exclude = ['user', 'intro_tour_completed', 'banned_from_comments',
                   'game_lab_transfer_process_on', 'active_in_current_semester',
                   'get_announcements_by_email']

    # UNIQUE if NOT NULL
    def clean_alias(self):
        return self.cleaned_data['alias'] or None

# class ProfileForm(forms.Form):
#     class Meta:
#         model = Profile
#         # fields = ['name','xp']
#         widgets = {
#
#         }
#         fields = '__all__'

# class ProfileUpdateForm(forms.ModelForm):
#     class Meta:
#         model = Profile
#         fields = '__all__'
