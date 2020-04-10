from django import forms

from allauth.account.forms import SignupForm


class CustomSignupForm(SignupForm):
    first_name = forms.CharField(
        max_length=30,
        label='First name',
        help_text="Please use the name that matches your school records.  You can put a different name in your profile.")  # noqa
    last_name = forms.CharField(
        max_length=30,
        label='Last name',
        help_text='Please use the name that matches your school records.')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].help_text = 'Ask your teacher what you should be using for your username.'

    def signup(self, request, user):
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.save()
        return user
