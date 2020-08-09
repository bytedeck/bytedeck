from django.forms import ModelForm

from captcha.fields import ReCaptchaField

from .models import Tenant


class TenantForm(ModelForm):
    class Meta:
        model = Tenant
        fields = ['name', 'captcha']

    captcha = ReCaptchaField()
