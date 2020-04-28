from django import forms

from allauth.account.forms import SignupForm
from siteconfig.models import SiteConfig


class CustomSignupForm(SignupForm):

    first_name = forms.CharField(
        max_length=30,
        label='First name',
        help_text="Please use the name that matches your school records.  You can put a different name in your profile." # noqa
    )

    last_name = forms.CharField(
        max_length=30,
        label='Last name',
        help_text='Please use the name that matches your school records.'
    )

    access_code = forms.CharField(
        max_length=128,
        label='Access Code',
        help_text='Enter the access code provided to you by your teacher.'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].help_text = 'Ask your teacher what you should be using for your username.'

    def clean(self):
        super(CustomSignupForm, self).clean()
        access_code = self.cleaned_data['access_code']
        if access_code != SiteConfig.get().access_code:
            raise forms.ValidationError("Access code unrecognized.")
