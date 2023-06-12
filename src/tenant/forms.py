from django import forms
from django.forms import ModelForm

from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Invisible
from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

from .models import Tenant


class TenantForm(ModelForm):
    class Meta:
        model = Tenant
        fields = ['name', 'captcha']

    # captcha = ReCaptchaField()
    captcha = ReCaptchaField(
        label='',
        widget=ReCaptchaV2Invisible
    )


class SendEmailForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)

    subject = forms.CharField(
        widget=forms.TextInput(attrs={"placeholder": "Subject"}))
    message = forms.CharField(widget=ByteDeckSummernoteSafeWidget)
