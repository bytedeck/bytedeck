from django import forms

from .models import Announcement

class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        exclude = ['author']

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
