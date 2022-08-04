from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from model_bakery import baker

from djcytoscape.models import CytoScape
from hackerspace_online.tests.utils import ViewTestUtilsMixin

from .test_models import generate_real_primary_map

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

        self.assertRedirectsLogin('djcytoscape:index')

        self.assertRedirectsLogin('djcytoscape:primary')
        self.assertRedirectsLogin('djcytoscape:quest_map', args=[1])
        self.assertRedirectsLogin('djcytoscape:quest_map_personalized', args=[1, 1])
        self.assertRedirectsLogin('djcytoscape:quest_map_interlink', args=[1, 1, 1])

        self.assertRedirectsLogin('djcytoscape:list')
        self.assertRedirectsLogin('djcytoscape:regenerate', args=[1])
        self.assertRedirectsLogin('djcytoscape:regenerate_all')
        self.assertRedirectsLogin('djcytoscape:generate_map', kwargs={'quest_id': 1, 'scape_id': 1})
        self.assertRedirectsLogin('djcytoscape:generate_unseeded')
        self.assertRedirectsLogin('djcytoscape:update', args=[1])
        self.assertRedirectsLogin('djcytoscape:delete', args=[1])

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

        self.assert403('djcytoscape:update', args=[self.map.id])
        self.assert403('djcytoscape:delete', args=[self.map.id])
        self.assert403('djcytoscape:regenerate', args=[self.map.id])
        self.assert403('djcytoscape:regenerate_all')
        self.assert403('djcytoscape:generate_map', kwargs={'quest_id': 1, 'scape_id': 1})
        self.assert403('djcytoscape:generate_unseeded')

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


class PrimaryViewTests(ViewTestUtilsMixin, TenantTestCase):

    def test_initial_map_generated_on_first_view(self):
        # shouldn't be any maps from the start
        self.assertFalse(CytoScape.objects.exists())

        # log in anoyone
        self.client = TenantClient(self.tenant)
        anyone = User.objects.create_user('anyone', password="password")
        success = self.client.login(username=anyone.username, password="password")
        self.assertTrue(success)

        # Access the primary map view
        self.assert200('djcytoscape:primary')

        # Should have generated the "Main" map
        self.assertEqual(CytoScape.objects.count(), 1)
        self.assertTrue(CytoScape.objects.filter(name="Main").exists())


class RegenerateViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.map = generate_real_primary_map()
        self.client = TenantClient(self.tenant)
        self.staff_user = User.objects.create_user(username="test_staff_user", password="password", is_staff=True)
        self.client.force_login(self.staff_user)

    def test_regenerate(self):
        self.assertRedirects(
            response=self.client.get(reverse('djcytoscape:regenerate', args=[self.map.id])),
            expected_url=reverse('djcytoscape:quest_map', args=[self.map.id]),
        )

    def test_regenerate_with_deleted_object(self):
        bad_map = CytoScape.objects.create(
            name="bad map",
            initial_content_type=ContentType.objects.get(app_label='quest_manager', model='quest'),
            initial_object_id=99999,  # a non-existant object
        )
        self.assertRedirects(
            response=self.client.get(reverse('djcytoscape:regenerate', args=[bad_map.id])),
            expected_url=reverse('djcytoscape:primary'),
        )

    def test_regenerate_all(self):
        self.assertRedirects(
            response=self.client.get(reverse('djcytoscape:regenerate_all')),
            expected_url=reverse('djcytoscape:primary'),
        )

    def test_regenerate_all_with_bad_map(self):
        CytoScape.objects.create(
            name="bad map",
            initial_content_type=ContentType.objects.get(app_label='quest_manager', model='quest'),
            initial_object_id=99999,  # a non-existant object
        )
        self.assertRedirects(
            response=self.client.get(reverse('djcytoscape:regenerate_all')),
            expected_url=reverse('djcytoscape:primary'),
        )
