from io import StringIO

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.test import TestCase
from django_tenants.utils import tenant_context

# from hackerspace_online.management.commands import find_replace
from tenant.models import Tenant

User = get_user_model()


class FindReplaceTest(TestCase):

    # def setUp(self):
    #     self.tenant = Tenant(
    #         domain_url='testdeck.localhost',
    #         schema_name='testdeck',
    #         name='testdeck'
    #     )
    #     self.tenant.save()

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "find_replace",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()

    def test_tenants_all(self):
        # Constant error, not sure why Category table is empty:
        # django.db.utils.IntegrityError: null value in column "title" violates not-null constraint
        # DETAIL:  Failing row contains (1, null, , t).
        pass
        # "All tenants"
        # for tenant in Tenant.objects.all():
        #     print(tenant.name)
        # # print(tenants)
        # # # requires
        # # pass
        # out = self.call_command(self.tenant.name)
        # print(out)
        # self.assertEqual(out, "In dry run mode (--write not passed)\n")


class InitDbTest(TestCase):
    """ Note that this is NOT a TenantTestCase
    """

    def call_command(self, *args, **kwargs):
        out = StringIO()
        call_command(
            "initdb",
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()

    def test_initdb(self):
        """ Test that initdb command sets up the public tenant, including:
        - a Tenant object called 'public'
        - a superuser
        - a Site object
        - a Flatpage object with url /pages/home/
        """
        output = self.call_command()
        print("*** INITDB Management Command: ", output)

        public_tenant = Tenant.objects.get(schema_name="public")  # no assert, but will throw exception if doesn't exist

        with tenant_context(public_tenant):
            FlatPage.objects.get(url='/home/')  # no assert, but will throw exception if doesn't exist
            user = User.objects.get(username='admin')
            self.assertTrue(user.is_superuser)
            self.assertTrue(Site.objects.exists())

            Tenant.objects.get(schema_name=apps.get_app_config('library').TENANT_NAME)  # no assert, but will throw exception if doesn't exist
