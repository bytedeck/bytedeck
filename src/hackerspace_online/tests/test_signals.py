from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin

# from django.shortcuts import reverse
# from django.test import RequestFactory


User = get_user_model()


class SignalTest(ViewTestUtilsMixin, TenantTestCase):
    def setUp(self):
        self.client = TenantClient(self.tenant)

    def change_domain_urls_signal(self):
        # TODO
        pass
