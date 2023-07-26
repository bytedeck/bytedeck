from django import forms
from django.forms import ModelForm

from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Invisible

from .models import Tenant


class TenantForm(ModelForm):

    first_name = forms.CharField(
        max_length=30,
        required=True,
        label="First name",
    )
    last_name = forms.CharField(
        max_length=30,
        required=True,
        label="Last name",
    )
    email = forms.EmailField(required=True)

    captcha = ReCaptchaField(label="", widget=ReCaptchaV2Invisible)

    class Meta:
        model = Tenant
        fields = ["name", "first_name", "last_name", "email", "captcha"]

    def clean_name(self):
        name = self.cleaned_data["name"]
        # has already validated the model field at this point
        if name == "public":
            raise forms.ValidationError("The public tenant is restricted and cannot be edited")
        else:
            from django_tenants.utils import schema_exists

            # finally, check that there isn't a schema on the db that doesn't have a tenant object
            # and thus doesn't care about name validation/uniqueness.
            if not self._meta.model.objects.filter(schema_name=name).exists() and schema_exists(name):
                raise forms.ValidationError(
                    f"The schema \"{name}\" already exists in database, and must be "
                    "deleted manually before creating tenant object with this name.",
                )

        return name
