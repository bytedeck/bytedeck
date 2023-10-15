# With help from https://stackoverflow.com/questions/6498488/testing-admin-modeladmin-in-django
import random
import string

from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase

from tenant.forms import TenantForm
from tenant.models import Tenant

User = get_user_model()


class TenantFormTest(TenantTestCase):
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
