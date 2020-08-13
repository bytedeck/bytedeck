# from django.db import connection
from django.http import HttpResponse, Http404
from django.test import RequestFactory

# from mock import patch

from tenant_schemas.test.cases import TenantTestCase
# from tenant_schemas.utils import get_public_schema_name

# from tenant_schemas.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin

# from tenant.models import Tenant
from tenant.views import public_only_view, non_public_only_view


class ViewsTest(ViewTestUtilsMixin, TenantTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        # self.client = TenantClient(self.tenant)

    def test_public_only_view(self):

        # Create a view for testing the mixin
        @public_only_view
        def view_accessible_by_public_only(request):
            return HttpResponse(status=200)

        # generate a request instance so we can call our view directly
        request = self.factory.get('/')

        # We're in the test tenant, so shouldn't be able to access:
        with self.assertRaises(Http404):
            view_accessible_by_public_only(request)

        # patch public tenant connection (mock the object?)  HOW?
        # with patch('tenant.views.connection.schema_name', return_value=get_public_schema_name()):
        # with patch.object('tenant.views.connection', 'schema_name', get_public_schema_name()):
        #     response = view_accessible_by_public_only(request)  
        #     self.assertEqual(response.status_code, 200)

    def test_non_public_only_view(self):

        # Create a view for testing the mixin
        @non_public_only_view
        def view_accessible_by_non_public_only(request):
            return HttpResponse(status=200)

        # generate a request instance so we can call our view directly
        request = self.factory.get('/nowhere/')

        # By default we are in the "test" tenant, so should be able to use the view
        response = view_accessible_by_non_public_only(request)  
        self.assertEqual(response.status_code, 200)

        # Should NOT be able to access from the public tenant:
        # Need to mock the connection
        # with self.assertRaises(Http404):
        #     view_accessible_by_non_public_only(request)
