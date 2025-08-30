from captcha.fields import ReCaptchaField
from captcha.widgets import ReCaptchaV2Checkbox

from django import forms
from django.contrib.auth import get_user_model
from django.forms import ModelForm

from siteconfig.models import SiteConfig
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

    def __init__(self, *args, **kwargs):
        """
        Initialize the TenantForm.

        If `verified_data` is provided in kwargs, pre-fill the form fields
        from it and disable the email field so that it cannot be modified.

        Args:
            *args: Positional arguments passed to the parent form.
            **kwargs: Keyword arguments passed to the parent form. Can include:
                verified_data (dict, optional): Dictionary containing pre-verified
                    user data with keys 'deck_name', 'first_name', 'last_name', 'email'.
        """
        # Pop verified data from kwargs (if any)
        self.verified_data = kwargs.pop("verified_data", None)
        super().__init__(*args, **kwargs)
        if self.verified_data:
            # Pre-fill fields from verified session
            self.fields["name"].initial = self.verified_data.get("deck_name", "")
            self.fields["first_name"].initial = self.verified_data.get("first_name", "")
            self.fields["last_name"].initial = self.verified_data.get("last_name", "")
            self.fields["email"].initial = self.verified_data.get("email", "")

            # Email is already verified so make it immutable
            self.fields["email"].disabled = True

    def clean_email(self):
        """
        Ensure the email field has a valid value during form cleaning.

        Returns the initial verified email if the field is disabled,
        otherwise returns the cleaned data from user input.

        Returns:
            str: The email address for the tenant owner.
        """
        if self.fields["email"].disabled:
            if self.verified_data and self.verified_data.get("email"):
                return self.verified_data["email"]
            return self.initial.get("email")
        return self.cleaned_data.get("email")

    def save(self, commit=True):
        """
        Save the Tenant and ensure the deck owner User has the correct email and names.
        """
        tenant = super().save(commit=False)

        email = self.cleaned_data.get("email") or self.initial.get("email")
        first_name = self.cleaned_data.get("first_name")
        last_name = self.cleaned_data.get("last_name")

        if commit:
            tenant.save()

            # Assign owner via SiteConfig
            owner = SiteConfig.get().deck_owner
            owner.email = email
            owner.first_name = first_name
            owner.last_name = last_name
            owner.save()

        return tenant


class DeckRequestForm(forms.Form):
    first_name = forms.CharField(
        max_length=150,
        label="First Name",
        widget=forms.TextInput(attrs={"placeholder": "Your first name"})
    )
    last_name = forms.CharField(
        max_length=150,
        label="Last Name",
        widget=forms.TextInput(attrs={"placeholder": "Your last name"})
    )
    email = forms.EmailField(
        label="Your Email",
        widget=forms.EmailInput(attrs={"placeholder": "you@example.com"})
    )
    captcha = ReCaptchaField(widget=ReCaptchaV2Checkbox)
