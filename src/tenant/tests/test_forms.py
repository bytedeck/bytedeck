# With help from https://stackoverflow.com/questions/6498488/testing-admin-modeladmin-in-django
import random
import string

from django.contrib.auth import get_user_model

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from django_recaptcha.widgets import ReCaptchaV2Invisible

from tenant.forms import MAX_DECK_NAME_LENGTH, DeckRequestForm, TenantForm
from tenant.models import Tenant

User = get_user_model()


class DeckRequestFormTest(ByteDeckTenantTestCase):
    """Tests for the public `DeckRequestForm`."""

    def test_captcha_uses_invisible_recaptcha_widget(self):
        """The deck request captcha must use the same reCAPTCHA widget type as the rest
        of the site (v2 invisible). A single key pair is configured globally
        (RECAPTCHA_PUBLIC_KEY/RECAPTCHA_PRIVATE_KEY) and Google's keys are widget-type
        specific, so a checkbox widget can't validate with the site's invisible keys.
        """
        form = DeckRequestForm()
        self.assertIsInstance(form.fields['captcha'].widget, ReCaptchaV2Invisible)


class TenantFormTest(ByteDeckTenantTestCase):
    """Various tests for `TenantForm` form class."""

    def test_default(self):
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

    def test_form_max_length(self):
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

    def test_cant_use_public_name(self):
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

    def test_cant_create_if_schema_still_exists(self):
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

    def test_clean_name__deck_name_too_long(self):
        """A deck name longer than MAX_DECK_NAME_LENGTH is rejected on the form with a
        clear error, so the user gets feedback instead of the name being silently
        truncated (into SiteConfig.site_name_short etc.) when the deck is created.
        """
        base = {"first_name": "John", "last_name": "Doe", "email": "john.doe@example.com"}

        # one over the limit: rejected with a message that names the limit
        too_long = "a" * (MAX_DECK_NAME_LENGTH + 1)
        form = TenantForm({**base, "name": too_long})
        self.assertFalse(form.is_valid())
        self.assertIn("name", form.errors)
        self.assertIn(str(MAX_DECK_NAME_LENGTH), form.errors["name"][0])

        # exactly at the limit: accepted
        at_limit = "a" * MAX_DECK_NAME_LENGTH
        form = TenantForm({**base, "name": at_limit})
        self.assertTrue(form.is_valid(), form.errors)

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
