from django.urls import reverse

from django_tenants.test.client import TenantClient

from hackerspace_online.tests.utils import ByteDeckTenantTestCase


class TestByteDeckSummernoteView(ByteDeckTenantTestCase):
    def setUp(self):
        """Set up a tenant-aware test client."""
        self.client = TenantClient(self.tenant)

    def test_url__editor_view_responds(self):
        """Customized view class is configured and respond"""
        url = reverse("bytedeck_summernote-editor", kwargs={"id": "foobar"})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
