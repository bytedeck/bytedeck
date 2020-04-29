from django.contrib.auth import get_user_model
# from django.urls import reverse
from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

# from siteconfig.models import SiteConfig
from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


class ViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        
        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)

        self.map = baker.make('djcytoscape.CytoScape')
              
    def test_all_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to home page  '''

        self.assertRedirectsHome('djcytoscape:index')

        self.assertRedirectsHome('djcytoscape:primary')
        self.assertRedirectsHome('djcytoscape:quest_map', args=[1])
        self.assertRedirectsHome('djcytoscape:quest_map_personalized', args=[1, 1])
        self.assertRedirectsHome('djcytoscape:quest_map_interlink', args=[1, 1, 1])

        self.assertRedirectsHome('djcytoscape:list')
        self.assertRedirectsAdmin('djcytoscape:regenerate', args=[1])
        self.assertRedirectsAdmin('djcytoscape:regenerate_all')
        self.assertRedirectsAdmin('djcytoscape:generate_map', kwargs={'quest_id': 1, 'scape_id': 1})
        self.assertRedirectsAdmin('djcytoscape:generate_unseeded')
        self.assertRedirectsAdmin('djcytoscape:update', args=[1])
        self.assertRedirectsAdmin('djcytoscape:delete', args=[1])

    def test_all_page_status_codes_for_students(self):
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        self.assert200('djcytoscape:index')
        self.assert200('djcytoscape:quest_map_personalized', args=[self.map.id, self.test_student1.id])
        # need to build  interlinked maps to test this.  Do in own test
        # self.assert200('djcytoscape:quest_map_interlink', args=[1, 1, 1])
        self.assert200('djcytoscape:list')
        self.assert200('djcytoscape:primary')
        self.assert200('djcytoscape:quest_map', args=[self.map.id])

        self.assertRedirectsAdmin('djcytoscape:update', args=[self.map.id])
        self.assertRedirectsAdmin('djcytoscape:delete', args=[self.map.id])
        self.assertRedirectsAdmin('djcytoscape:regenerate', args=[self.map.id])
        self.assertRedirectsAdmin('djcytoscape:regenerate_all')
        self.assertRedirectsAdmin('djcytoscape:generate_map', kwargs={'quest_id': 1, 'scape_id': 1})
        self.assertRedirectsAdmin('djcytoscape:generate_unseeded')

    def test_all_page_status_codes_for_teachers(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        self.assert200('djcytoscape:index')
        self.assert200('djcytoscape:quest_map_personalized', args=[self.map.id, self.test_student1.id])
        # need to build  interlinked maps to test this.  Do in own test
        # self.assert200('djcytoscape:quest_map_interlink', args=[1, 1, 1])
        self.assert200('djcytoscape:list')
        self.assert200('djcytoscape:primary')
        self.assert200('djcytoscape:quest_map', args=[self.map.id])

        self.assert200('djcytoscape:update', args=[self.map.id])
        self.assert200('djcytoscape:delete', args=[self.map.id])

        # These will need their own tests:
        # self.assert200('djcytoscape:regenerate', args=[self.map.id])
        # self.assert200('djcytoscape:regenerate_all')
        # self.assert200('djcytoscape:generate_map', kwargs={'quest_id': 1, 'scape_id': 1})
        # self.assert200('djcytoscape:generate_unseeded')
