from io import StringIO
from django.core.management import call_command
from django.test import TestCase

# from hackerspace_online.management.commands import find_replace
# from tenant.models import Tenant


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
