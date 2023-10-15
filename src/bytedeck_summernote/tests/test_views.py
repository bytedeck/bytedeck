from django.urls import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient


class TestByteDeckSummernoteView(TenantTestCase):
    def setUp(self):
        self.client = TenantClient(self.tenant)

    def test_url(self):
        """Customized view class is configured and respond"""
        url = reverse("bytedeck_summernote-editor", kwargs={"id": "foobar"})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
