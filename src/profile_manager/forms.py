from django import forms

from .models import Profile

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        exclude = ['user']

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
