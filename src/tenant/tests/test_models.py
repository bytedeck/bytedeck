from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from django_tenants.utils import get_public_schema_name, schema_context
from freezegun import freeze_time
from model_bakery import baker
from hackerspace_online import settings
from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from tenant.models import Tenant, check_tenant_name, default_trial_end_date

User = get_user_model()


class TenantModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Build an extra tenant on a localhost domain to exercise dev-domain behavior."""
        # TenantTestCase comes with a `cls.tenant` already, but let make another so we can test development
        # stuff on localhost domain
        with schema_context(get_public_schema_name()):
            cls.tenant_localhost = Tenant(
                schema_name='my_development_schema',
                name='my_name'
            )
            cls.tenant_localhost.save()
            domain = cls.tenant_localhost.get_primary_domain()
            domain.domain = 'my-dev-schema.localhost'
            domain.save()

    def test_tenant_test_case__provides_configured_tenant(self):
        """ From docs: https://django-tenant-schemas.readthedocs.io/en/latest/test.html
        If you want a test to happen at any of the tenant’s domain, you can use the test case TenantTestCase.
        It will automatically create a tenant for you, set the connection’s schema to tenant’s schema and
        make it available at `self.tenant`
        """
        self.assertIsInstance(self.tenant, Tenant)
        self.assertEqual(self.tenant.schema_name, 'test')
        self.assertEqual(str(self.tenant), f'{self.tenant.schema_name} - {self.tenant.primary_domain_url}')

    def test_tenant_creation__localhost_tenant_created(self):
        """A tenant created on a localhost domain is a valid Tenant instance."""
        self.assertIsInstance(self.tenant_localhost, Tenant)

    def test_get_root_url__https_and_localhost(self):
        """get_root_url returns an https URL for a real domain and an http localhost URL for a dev tenant."""
        self.assertEqual(self.tenant.get_root_url(), "https://tenant.test.com")
        self.assertEqual(self.tenant_localhost.get_root_url(), "http://my-dev-schema.localhost:8000")

    def test_last_staff_login__populated_excluding_admin(self):
        """ When a staff logins to a tenant, the last_staff_login should have the correct value,
        should not include the admin account
        """
        self.assertIsNone(self.tenant.last_staff_login)

        staff = baker.make(User, is_staff=True)
        self.client.force_login(staff)
        self.tenant.update_cached_fields()

        staff.refresh_from_db()
        self.assertIsNotNone(self.tenant.last_staff_login)
        self.assertEqual(self.tenant.last_staff_login, staff.last_login)

        # if admin account logs in, should not change the result
        admin = User.objects.get(username=settings.TENANT_DEFAULT_ADMIN_USERNAME)
        self.client.force_login(admin)
        self.tenant.update_cached_fields()
        admin.refresh_from_db()
        # should still return the staff user's last log in, ignoring the admin user
        self.assertEqual(self.tenant.last_staff_login, staff.last_login)


class CheckTenantNameTest(SimpleTestCase):
    """ A tenant's name is used for both the schema_name and as the subdomain in the
    tenant's domain_url field, so {name} it must be valid for a schema and a url.
    """

    def test_check_tenant_name__underscore_invalid(self):
        """A name containing underscores is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, 'tenant_name_with_underscores')

    def test_check_tenant_name__special_chars_invalid(self):
        """A name containing special characters is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, 'tenant@')

    def test_check_tenant_name__number_start_invalid(self):
        """A name starting with a number is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, '9tenant')

    def test_check_tenant_name__uppercase_invalid(self):
        """A name containing uppercase letters is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, 'Tenant')

    def test_check_tenant_name__start_dash_invalid(self):
        """A name starting with a dash is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, '-tenant')

    def test_check_tenant_name__end_dash_invalid(self):
        """A name ending with a dash is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, 'tenant-')

    def test_check_tenant_name__multidash_invalid(self):
        """A name with consecutive dashes is rejected."""
        self.assertRaises(ValidationError, check_tenant_name, 'ten--ant')

    def test_check_tenant_name__mid_dash_valid(self):
        """A name with a single mid-string dash is accepted."""
        check_tenant_name('ten-ant')

    def test_check_tenant_name__multi_mid_dash_valid(self):
        """A name with multiple non-consecutive mid-string dashes is accepted."""
        check_tenant_name('ten-an-t')

    def test_check_tenant_name__mid_number_valid(self):
        """A name with numbers after the first character is accepted."""
        check_tenant_name('t3nan4')


class DefaultTrialEndDateTest(SimpleTestCase):
    """Tests for the default demo/trial expiry date on new tenants (Issue #1146).

    A new deck's trial runs for 60 days, so ``Tenant.trial_end_date`` defaults to
    ``today + 60 days``. Time is frozen so "today" is deterministic.
    """

    @freeze_time("2024-02-29")  # a leap day, so the +60 arithmetic can't be faked with month math
    def test_default_trial_end_date__is_60_days_from_today(self):
        """The default_trial_end_date() helper returns exactly 60 days from today."""
        self.assertEqual(default_trial_end_date(), date(2024, 2, 29) + timedelta(days=60))

    @freeze_time("2024-02-29")
    def test_new_tenant__trial_end_date_defaults_to_60_days_out(self):
        """A newly built Tenant gets trial_end_date defaulted to today + 60 days."""
        # Field defaults are applied at instantiation, so no save() (and no DB) is needed.
        tenant = Tenant(schema_name="demo", name="demo")
        self.assertEqual(tenant.trial_end_date, date(2024, 2, 29) + timedelta(days=60))
