from django.contrib.auth import get_user_model
from django.shortcuts import reverse

from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


class ViewsTest(ViewTestUtilsMixin, TenantTestCase):
    def setUp(self):
        # Every test needs access to the request factory.
        # https://docs.djangoproject.com/en/3.0/topics/testing/advanced/#the-request-factory
        # self.factory = RequestFactory()
        self.client = TenantClient(self.tenant)

    def test_home_view_staff(self):
        staff_user = User.objects.create_user(username="test_staff_user", password="password", is_staff=True)
        self.client.force_login(staff_user)
        response = self.client.get(reverse('home'))
        self.assertRedirects(
            response,
            reverse('quests:approvals')
        )

    def test_home_view_authenticated(self):
        user = User.objects.create_user(username="test_user", password="password")
        self.client.force_login(user)
        self.assertRedirectsQuests('home')
    
    def test_home_view_anonymous(self):
        self.assert200('home')

    def test_secret_view(self):
        self.assert200('simple')
