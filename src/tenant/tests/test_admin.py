# With help from https://stackoverflow.com/questions/6498488/testing-admin-modeladmin-in-django

from django.contrib.admin.sites import AdminSite
# from django.core.exceptions import ValidationError

from django_tenants.test.cases import TenantTestCase
# from django_tenants.test.client import TenantClient
from django_tenants.utils import tenant_context
from django.utils import timezone

from tenant.admin import TenantAdmin, TenantAdminForm
from tenant.models import Tenant


class NonPublicTenantAdminTest(TenantTestCase):
    """For testing non-public tenants

    TenantTestCase comes with a `self.tenant`

    From docs: https://django-tenant-schemas.readthedocs.io/en/latest/test.html
        If you want a test to happen at any of the tenant’s domain, you can use the test case TenantTestCase.
        It will automatically create a tenant for you, set the connection’s schema to tenant’s schema and
        make it available at `self.tenant`

    """

    def test_nonpublic_tenant_admin_save_model(self):
        tenant_model_admin = TenantAdmin(model=Tenant, admin_site=AdminSite())

        # Can't create tenant outside the `public` schema. Current schema is `test`, so should throw exception
        with self.assertRaises(Exception):
            tenant_model_admin.save_model(obj=Tenant(), request=None, form=None, change=None)


class PublicTenantTestAdminPublic(TenantTestCase):
    """TenantTestCase comes with a tenant: tenant.test.com"""

    ###############################################################################
    # Not sure why this doesn't work, but seems like TenantTestCase is
    # stops using the test databse and is looking for the real databse? or something...
    # So it fails on TravisCI where there is no database names `postgress`
    ###############################################################################
    # fixtures = ['tenant/tenants.json']

    # # This doesn't seem to work when placed in SetUp, so make them class variables.
    # tenant_model_admin = TenantAdmin(model=Tenant, admin_site=AdminSite())
    # public_tenant = Tenant.objects.get(schema_name="public")

    # def test_public_tenant_exists(self):
    #     self.assertIsInstance(self.public_tenant, Tenant)
    #     self.assertEqual(self.public_tenant.domain_url, "localhost")
    #################################################################################

    def setUp(self):
        # create the public schema
        self.public_tenant = Tenant(
            schema_name='public',
            name='public'
        )
        self.tenant_model_admin = TenantAdmin(model=Tenant, admin_site=AdminSite())

    def test_public_tenant_admin_save_model(self):

        with tenant_context(self.public_tenant):
            non_public_tenant = Tenant(
                name="Non-Public",  # Not a valid name, but not validated in this test
            )

            # public tenant should be able to create new tenant/schemas
            self.tenant_model_admin.save_model(obj=non_public_tenant, request=None, form=None, change=None)
            self.assertIsInstance(non_public_tenant, Tenant)
            # schema names should be all lower case and dashes converted to underscores
            self.assertEqual(non_public_tenant.schema_name, "non_public")

        # TODO: Not working, can't figure out why?
        # When try to use client.get() the context switches back to the public tenant
        # WHY!?!?

        # make sure we can access and sign-in to the new tenant
        # with tenant_context(non_public_tenant):
        #     from django.db import connection
        #     from django.contrib.auth import get_user_model
        #     from django.urls import reverse

        #     client = TenantClient(non_public_tenant)
        #     connection.set_tenant(non_public_tenant)
        #     print(connection.schema_name)  # non_public
        #     response = client.get(reverse('account_login'))
        #     print(connection.schema_name)  # public

        #     # self.assertEqual(response.status_code, 200)
        #     print(connection.schema_name)

        #     test_teacher = get_user_model().objects.create_user('test_teacher', password="password", is_staff=True)
        #     client = TenantClient(non_public_tenant)
        #     client.force_login(test_teacher)
        #     response = client.get(reverse('quests:quests'))
        #     self.assertEqual(response.status_code, 200)

    # FIXME:
    # def test_public_tenant_admin_save_new_tenant_with_bad_names(self):
    #
    #     with tenant_context(self.public_tenant):
    #         # tenant names with spaces should be rejected:
    #         with self.assertRaises(ValidationError):
    #             non_public_tenant_bad_name = Tenant(name="Non Public")
    #             self.tenant_model_admin.save_model(obj=non_public_tenant_bad_name, request=None, form=None, change=None)
    #         # also other alpha-numeric characters except dashes and underscores
    #         with self.assertRaises(ValidationError):
    #             non_public_tenant_bad_name = Tenant(name="Non*Public")
    #             self.tenant_model_admin.save_model(obj=non_public_tenant_bad_name, request=None, form=None, change=None)


class TenantAdminFormTest(TenantTestCase):

    def setUp(self):
        self.form_data = {
            'name': 'test',  # This is the name of the already existing test tenant
            # 'owner_full_name': None,
            # 'owner_email': None,
            'max_active_users': 50,
            'max_quests': 100,
            # 'paid_until': None,
            'trial_end_date': timezone.now()
        }

    def test_public_tenant_not_editable(self):
        self.form_data["name"] = "public"
        form = TenantAdminForm(self.form_data)
        self.assertFalse(form.is_valid())

    def test_new_non_public_tenant_valid(self):
        self.form_data["name"] = "non-public"
        form = TenantAdminForm(self.form_data)
        self.assertTrue(form.is_valid())

    def test_existing_non_public_tenant_valid(self):
        """ test tenant already exists as a part of the TenantTestCase """
        form = TenantAdminForm(self.form_data)
        self.assertTrue(form.is_valid())

    def test_cant_change_existing_name(self):
        # test tenant already exists and is connected in TenantTestCase
        self.form_data["name"] = "nottest"
        form = TenantAdminForm(self.form_data)
        form.instance = Tenant.get()  # test tenant with schema 'test'
        self.assertFalse(form.is_valid())
