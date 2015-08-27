from django import forms

from .models import CourseStudent

class CourseStudentForm(forms.ModelForm):
    class Meta:
        model = CourseStudent
        exclude = ['user','active']

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
