# With help from https://stackoverflow.com/questions/6498488/testing-admin-modeladmin-in-django
from django_tenants.test.cases import TenantTestCase

from tenant.forms import TenantForm
from tenant.models import Tenant


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
