from django_recaptcha.fields import ReCaptchaField
from django_recaptcha.widgets import ReCaptchaV2Invisible

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

    def __init__(self, *args, **kwargs):
        """Initialize the form and surface the deck-name length limit in its help text.

        The deck name becomes the deck's subdomain/schema, so the only real cap is the
        model field's ``max_length`` (the longest a Postgres schema — and therefore the
        URL — can be). It is no longer tied to the shorter ``site_name_short`` display
        field, which is truncated from the name at creation time instead. Appending the
        limit to the help text tells requesters the cap up front (#1975).
        """
        super().__init__(*args, **kwargs)
        max_len = Tenant._meta.get_field("name").max_length
        self.fields["name"].help_text += f". The name can be at most {max_len} characters long."

    def clean_name(self):
        """Validate the deck name.

        Rejects the reserved ``public`` name and a name whose schema already exists in
        the database without a matching tenant object. The length and format are already
        enforced by the model field (``max_length`` and ``check_tenant_name``).

        Returns:
            str: The cleaned deck name.

        Raises:
            forms.ValidationError: If the name is reserved or collides with an existing
                orphaned schema.
        """
        name = self.cleaned_data["name"]
        # has already validated the model field (format, length, uniqueness) at this point
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
                    user data with keys 'first_name', 'last_name', 'email'.

        Returns:
            None
        """
        # Pop verified data from kwargs (if any)
        self.verified_data = kwargs.pop('verified_data', None)
        super().__init__(*args, **kwargs)
        if self.verified_data:
            # Pre-fill fields from verified session
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
            email = (self.verified_data or {}).get("email") or self.initial.get("email")
            if not email:
                raise forms.ValidationError("Verified e-mail address is required.")
            return email
        return self.cleaned_data.get("email")

    def save(self, commit=True):
        """
        Save and return the Tenant.

        The deck owner (names, email, password, verification) is set up by
        TenantCreate.form_valid inside the new tenant's schema context. It is
        deliberately not done here: this form runs in the public schema, where
        SiteConfig.get() returns None, so any owner update here would either be
        a no-op or touch the wrong schema.

        Args:
            commit (bool): When True (default), validate and persist the Tenant
                to the database. When False, return the unsaved instance.

        Returns:
            Tenant: The Tenant instance (saved when ``commit`` is True).
        """
        tenant = super().save(commit=False)
        if commit:
            tenant.full_clean()
            tenant.save()
        return tenant


class DeckRequestForm(forms.Form):
    """Public form to request a new deck; protected by reCAPTCHA."""

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
    # Must match the widget type of the site's reCAPTCHA keys: a single key pair is
    # configured globally and Google's keys are widget-type specific, so use the same
    # invisible widget as the public contact form (see hackerspace_online/forms.py).
    captcha = ReCaptchaField(label='', widget=ReCaptchaV2Invisible)
