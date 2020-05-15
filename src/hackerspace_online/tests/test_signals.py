from django.contrib.auth import get_user_model
# from django.shortcuts import reverse
# from django.test import RequestFactory

from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


class SignalTest(ViewTestUtilsMixin, TenantTestCase):
    def setUp(self):
        self.client = TenantClient(self.tenant)

    def change_domain_urls_signal(self):
        # TODO
        pass
