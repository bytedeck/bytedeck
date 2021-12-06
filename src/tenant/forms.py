from django.forms import ModelForm

from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Invisible

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
