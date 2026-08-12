# With help from https://stackoverflow.com/questions/6498488/testing-admin-modeladmin-in-django
import random
import string

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from django_recaptcha.widgets import ReCaptchaV2Invisible

from tenant.forms import DeckRequestForm, TenantForm
from tenant.models import Tenant

User = get_user_model()


class DeckRequestFormTest(ByteDeckTenantTestCase):
    """Tests for the public `DeckRequestForm`."""

    def test_captcha__uses_invisible_recaptcha_widget(self):
        """The deck request captcha must use the same reCAPTCHA widget type as the rest
        of the site (v2 invisible). A single key pair is configured globally
        (RECAPTCHA_PUBLIC_KEY/RECAPTCHA_PRIVATE_KEY) and Google's keys are widget-type
        specific, so a checkbox widget can't validate with the site's invisible keys.
        """
        form = DeckRequestForm()
        self.assertIsInstance(form.fields['captcha'].widget, ReCaptchaV2Invisible)


class TenantFormTest(ByteDeckTenantTestCase):
    """Various tests for `TenantForm` form class."""

    def test_is_valid__complete_and_incomplete_data(self):
        """
        Creating new tenant object with valid data, should pass without errors.
        """
        # first case, submit incomplete (empty) form
        form = TenantForm(data={})
        self.assertFalse(form.is_valid())

        # second case, forgot to enter "first" and "last" names
        data = {
            "name": "default",
            "email": "john.doe@example.com",
        }
        form = TenantForm(data)
        self.assertFalse(form.is_valid())

        # third case, incorrect email address
        data = {
            "name": "default",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example",  # incorrect email address
        }
        form = TenantForm(data)
        self.assertFalse(form.is_valid())

        # final case, submit complete (full) form
        data = {
            "name": "default",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
        }
        form = TenantForm(data)
        self.assertTrue(form.is_valid())

    def test_max_length__fields_enforce_user_field_limits(self):
        """
        Test if form fields has set correct `max_length` property.
        """
        def generate_random_string(length=128):
            return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

        # first case, using `first_name` longer than `User.first_name` can accept,
        # should fail with form error
        data = {
            "first_name": generate_random_string(User._meta.get_field("first_name").max_length + 1),
        }
        form = TenantForm(data)
        self.assertEqual(form.errors["first_name"], ["Ensure this value has at most 150 characters (it has 151)."])

        # second case, using `last_name` longer than `User.last_name` can accept,
        # should fail with form error
        data = {
            "last_name": generate_random_string(User._meta.get_field("last_name").max_length + 1),
        }
        form = TenantForm(data)
        self.assertEqual(form.errors["last_name"], ["Ensure this value has at most 150 characters (it has 151)."])

        # third case, using `email` longer than `User.email` can accept,
        # should fail with form error
        data = {
            "email": generate_random_string(User._meta.get_field("email").max_length) + "@example.com",
        }
        form = TenantForm(data)
        self.assertEqual(form.errors["email"], ["Ensure this value has at most 254 characters (it has 266)."])

        # final case, submit complete (full) form
        data = {
            "name": "default",
            "first_name": generate_random_string(User._meta.get_field("first_name").max_length),
            "last_name": generate_random_string(User._meta.get_field("last_name").max_length),
            "email": generate_random_string(User._meta.get_field("email").max_length - 12) + "@example.com",
        }
        form = TenantForm(data)
        self.assertTrue(form.is_valid())

    def test_clean_name__cant_use_public_name(self):
        """
        Creating new tenant object with reserved "public" name, should fail with form (validation) error
        """
        data = {
            "name": "public",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
        }
        form = TenantForm(data)
        self.assertFalse(form.is_valid())

    def test_clean_name__cant_create_if_schema_still_exists(self):
        """
        Creating new tenant object with a name of existing schema, should fail with form (validation) error
        """
        data = {
            "name": "test",  # created by TenantTestCase parent class
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
        }
        # delete test tenant object without dropping schema
        Tenant.get().delete(force_drop=False)
        # trying to create new tenant, with name of existing schema
        form = TenantForm(data)
        self.assertFalse(form.is_valid())

    def test_clean_name__deck_name_capped_for_readable_urls(self):
        """New deck names are capped at DECK_NAME_MAX_LENGTH on the creation form:
        the name becomes the deck's subdomain, and a name at the model field's
        62-character Postgres schema limit makes an unreadable URL (maintainer
        decision, 2026-08-08). One over the cap is rejected, a name at the cap is
        accepted, and the model field itself still allows more so existing decks
        with longer names are unaffected."""
        from tenant.forms import DECK_NAME_MAX_LENGTH

        base = {"first_name": "John", "last_name": "Doe", "email": "john.doe@example.com"}

        form = TenantForm({**base, "name": "a" * (DECK_NAME_MAX_LENGTH + 1)})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

        form = TenantForm({**base, "name": "a" * DECK_NAME_MAX_LENGTH})
        self.assertTrue(form.is_valid(), form.errors)

        self.assertGreater(Tenant._meta.get_field("name").max_length, DECK_NAME_MAX_LENGTH)

    def test_name_help_text__includes_length_limit(self):
        """The deck-name field's help text states the cap (#1975), and the widget
        carries it as a maxlength attribute so the browser stops overtyping."""
        from tenant.forms import DECK_NAME_MAX_LENGTH

        form = TenantForm()
        self.assertIn(str(DECK_NAME_MAX_LENGTH), form.fields["name"].help_text)
        self.assertEqual(form.fields["name"].widget.attrs.get("maxlength"), DECK_NAME_MAX_LENGTH)

    def test_clean_name__duplicate_deck_name_is_rejected(self):
        """A deck name that already exists is rejected on the form (via the unique
        constraint), so the user is warned before the deck is created rather than
        hitting an error afterwards.
        """
        # Add an existing tenant with a known (short) name. bulk_create avoids the
        # slow schema build and the post_save signals — we only need the row so the
        # form's uniqueness check has something to collide with.
        Tenant.objects.bulk_create([Tenant(schema_name="dupedeck", name="dupedeck")])
        data = {
            "name": "dupedeck",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
        }
        form = TenantForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)

    def test_clean_email__disabled_without_verified_email_raises(self):
        """clean_email guards against a disabled email field with no verified address on record.

        It is called directly here: through full form validation the disabled required email
        field's own field-level clean raises 'This field is required.' first, so clean_email is
        never reached with an empty value. The guard exists as defense in depth, so we exercise
        the method itself.
        """
        # verified_data is truthy (so __init__ disables the field) but carries no email, and no
        # form-level initial email is supplied either, so clean_email has nothing to fall back on.
        form = TenantForm(
            data={"name": "noemaildeck", "first_name": "John", "last_name": "Doe"},
            verified_data={"first_name": "John", "last_name": "Doe"},
        )
        with self.assertRaises(ValidationError):
            form.clean_email()

    def test_save__commit_false_returns_unsaved_tenant(self):
        """save(commit=False) returns the built-but-unsaved Tenant (no pk, no schema build)."""
        form = TenantForm(data={
            "name": "commitfalse",
            "first_name": "John",
            "last_name": "Doe",
            "email": "john.doe@example.com",
        })
        self.assertTrue(form.is_valid(), form.errors)
        tenant = form.save(commit=False)
        self.assertIsNone(tenant.pk)
