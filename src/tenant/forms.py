from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Invisible
from django import forms
from django.contrib.auth import get_user_model
from django.forms import ModelForm

from .models import Tenant

User = get_user_model()


class TenantBaseForm(ModelForm):
    """
    Base form class for Tenant model.
    """

    class Meta:
        model = Tenant
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"]
        # has already validated the model field at this point
        if name == "public":
            raise forms.ValidationError("The public tenant is restricted and cannot be used.")
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


class TenantForm(TenantBaseForm):

    first_name = forms.CharField(
        max_length=User._meta.get_field("first_name").max_length,
        required=True,
        label="First name",
    )
    last_name = forms.CharField(
        max_length=User._meta.get_field("last_name").max_length,
        required=True,
        label="Last name",
    )
    email = forms.EmailField(
        max_length=User._meta.get_field("email").max_length,
        label="E-mail address",
        required=True,
    )

    class Meta(TenantBaseForm.Meta):
        fields = TenantBaseForm.Meta.fields + ["first_name", "last_name", "email"]


class ProspectForm(forms.Form):
    deck_name = forms.CharField(
        max_length=50,
        label='Deck Name',
        help_text='The name of your deck (DECKNAME.bytedeck.com)',
    )
    first_name = forms.CharField(
        max_length=30,
        label='First name',
        help_text='Please enter your first name',  # noqa
    )
    last_name = forms.CharField(max_length=30, label='Last name', help_text='Please enter your last name')
    email = forms.EmailField(required=True, help_text='')
    captcha = ReCaptchaField(label='', widget=ReCaptchaV2Invisible)

    def clean_deck_name(self):
        deck_name = self.cleaned_data['deck_name']

        if Tenant.objects.filter(name=deck_name).exists():
            raise forms.ValidationError('This deck name already exists')

        return deck_name

    def clean_email(self):
        email = self.cleaned_data['email']

        if Tenant.objects.filter(owner_email_cached=email).exists():
            raise forms.ValidationError('This e-mail is already in use.')

        return email
