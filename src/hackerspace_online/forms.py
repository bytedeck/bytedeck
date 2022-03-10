from smtplib import SMTPException

from django import forms
from django.core.mail import mail_admins
from django.utils.translation import gettext_lazy as _

from allauth.account.adapter import get_adapter
from allauth.account.forms import ResetPasswordForm, SignupForm, LoginForm
from allauth.account.utils import filter_users_by_email
from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Invisible

from siteconfig.models import SiteConfig


class CustomSignupForm(SignupForm):

    first_name = forms.CharField(
        max_length=30,
        label='First name',
        help_text="Please use the name that matches your school records.  You can put a different name in your profile."  # noqa
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
        self.fields['username'].help_text = 'Ask your teacher what you should be using for your username. Username is not case sensitive'

    def clean(self):
        super(CustomSignupForm, self).clean()
        access_code = self.cleaned_data['access_code']
        if access_code != SiteConfig.get().access_code:
            raise forms.ValidationError("Access code unrecognized.")


class CustomLoginForm(LoginForm):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['login'].help_text = 'Username is not case sensitive'


class PublicContactForm(forms.Form):
    name = forms.CharField(required=True)
    email = forms.EmailField(
        required=True,
        help_text='We will never share your email with anyone else.')
    message = forms.CharField(widget=forms.Textarea, required=True)

    # Not using because our recaptcha key is currently set up for checkbox only
    # and doesn't also support the invisible widget.
    captcha = ReCaptchaField(
        label='',
        widget=ReCaptchaV2Invisible
    )

    def send_email(self):
        email = self.cleaned_data["email"]
        name = self.cleaned_data["name"]
        message = self.cleaned_data["message"]

        try:
            mail_admins(
                subject=f"Contact from {name}",
                message=f"Name: {name}\nEmail: {email}\nMessage: {message}",
            )
        except SMTPException:
            return False

        return True


class CustomResetPasswordForm(ResetPasswordForm):

    def clean_email(self):
        email = self.cleaned_data["email"]
        email = get_adapter().clean_email(email)
        self.users = filter_users_by_email(email, is_active=True)
        if not self.users:
            raise forms.ValidationError(_("This e-mail address is not assigned to any active user account."
                                          " Please contact your teacher to have your password reset or to re-activate your account."))
        return self.cleaned_data["email"]
