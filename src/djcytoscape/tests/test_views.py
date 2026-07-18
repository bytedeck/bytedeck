from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from django_tenants.test.client import TenantClient
from model_bakery import baker
from unittest.mock import patch

from djcytoscape.models import CytoScape

from profile_manager.models import Profile
from hackerspace_online.tests.utils import ByteDeckTenantTestCase, ViewTestUtilsMixin, generate_form_data

User = get_user_model()


class ViewTests(ViewTestUtilsMixin, ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        # need a teacher and a student so tests can log in as each via force_login()

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student1 = User.objects.create_user('test_student')

        # Ensure profiles exist without duplicating them (in case a signal already created them)
        Profile.objects.get_or_create(user=cls.test_teacher)
        Profile.objects.get_or_create(user=cls.test_student1)

        cls.quest_ct = ContentType.objects.get(app_label='quest_manager', model='quest')
        # Pin this map's initial object to a dedicated quest. baker.make would
        # otherwise fill initial_content_type/initial_object_id with random
        # values that could (rarely, depending on baker's RNG state across a
        # multi-app run) collide with the object a POST test submits, which the
        # CytoscapeGFKChoiceField then excludes as "already in use" -- making the
        # form invalid only on unlucky orderings.
        cls.map_initial_quest = baker.make('quest_manager.Quest')
        cls.map = baker.make(
            'djcytoscape.CytoScape',
            initial_content_type=cls.quest_ct,
            initial_object_id=cls.map_initial_quest.id,
        )

    def setUp(self):
        self.client = TenantClient(self.tenant)

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
        self.client.force_login(self.test_student1)

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
        self.client.force_login(self.test_teacher)

        self.assert200('djcytoscape:index')
        self.assert200('djcytoscape:quest_map_personalized', args=[self.map.id, self.test_student1.id])
        # need to build  interlinked maps to test this.  Do in own test
        # self.assert200('djcytoscape:quest_map_interlink', args=[1, 1, 1])
        self.assert200('djcytoscape:list')
        self.assert200('djcytoscape:primary')
        self.assert200('djcytoscape:quest_map', args=[self.map.id])

        self.assert200('djcytoscape:update', args=[self.map.id])
        self.assert200('djcytoscape:delete', args=[self.map.id])

        self.assert200('djcytoscape:generate_unseeded')
        self.assert200('djcytoscape:generate_map', kwargs={'quest_id': 1, 'scape_id': self.map.id})

        # These will need their own tests:
        # self.assert200('djcytoscape:regenerate', args=[self.map.id])
        # self.assert200('djcytoscape:regenerate_all')

    def test_ScapeGenerateMap__POST(self):
        """ Assert a teacher can generate a map using ScapeGenerateMapView """
        from djcytoscape.forms import GenerateQuestMapForm

        self.client.force_login(self.test_teacher)

        # A dedicated, freshly-created quest as the initial object: it is not yet
        # used by any map, so the CytoscapeGFKChoiceField won't exclude it. Using
        # an unordered .objects.first() here made the test depend on which quest
        # happened to be first and whether it was already a map's initial object.
        content_type = self.quest_ct
        object_ = baker.make('quest_manager.Quest')

        form_data = generate_form_data(model_form=GenerateQuestMapForm, name='New Name')
        form_data.update({'initial_content_object': f'{content_type.id}-{object_.id}'})

        # check if map name exists
        self.assertFalse(CytoScape.objects.filter(name='New Name').exists())

        # response tests
        response = self.client.post(reverse('djcytoscape:generate_unseeded'), data=form_data)

        # assert map exists
        self.assertTrue(CytoScape.objects.filter(name='New Name').exists())

        # assert values are the same as form data values
        map_ = CytoScape.objects.get(name='New Name')
        self.assertEqual(map_.initial_content_type, content_type)
        self.assertEqual(map_.initial_object_id, object_.id)

        # assert redirects to quest_map page
        self.assertRedirects(response, reverse('djcytoscape:quest_map', args=[map_.pk]))

    def test_ScapeUpdateView__POST(self):
        """ Assert a teacher can update a map using ScapeGenerateMapView """
        from djcytoscape.forms import QuestMapForm

        self.client.force_login(self.test_teacher)

        # A dedicated quest (not used as any other map's initial object) so the
        # CytoscapeGFKChoiceField accepts it; see test_ScapeGenerateMap__POST.
        content_type = self.quest_ct
        object_ = baker.make('quest_manager.Quest')

        form_data = generate_form_data(model_form=QuestMapForm, name='Updated Name')
        form_data.update({'initial_content_object': f'{content_type.id}-{object_.id}'})

        with patch.object(CytoScape, 'regenerate') as mock_regenerate:
            # response tests
            response = self.client.post(reverse('djcytoscape:update', args=[self.map.pk]), data=form_data)

        self.assertRedirects(response, reverse('djcytoscape:quest_map', args=[self.map.pk]))

        # assert map exists
        self.assertTrue(CytoScape.objects.filter(name='Updated Name').exists())

        # assert values are updated
        map_ = CytoScape.objects.get(name='Updated Name')
        self.assertEqual(map_.initial_content_type, content_type)
        self.assertEqual(map_.initial_object_id, object_.id)

        # assert regenerate was called
        mock_regenerate.assert_called_once()


class PrimaryViewTests(ViewTestUtilsMixin, ByteDeckTenantTestCase):

    def test_initial_map_generated_on_first_view(self):
        # shouldn't be any maps from the start
        self.assertFalse(CytoScape.objects.exists())

        # log in anoyone
        self.client = TenantClient(self.tenant)
        anyone = User.objects.create_user('anyone')
        self.client.force_login(anyone)

        # Access the primary map view
        self.assert200('djcytoscape:primary')

        # Should have generated the "Main" map
        self.assertEqual(CytoScape.objects.count(), 1)
        self.assertTrue(CytoScape.objects.filter(name="Main").exists())


class RegenerateViewTests(ViewTestUtilsMixin, ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        from .test_models import generate_real_primary_map

        # regeneration in tests only touches the DB, which is rolled back per test
        cls.map = generate_real_primary_map()
        cls.staff_user = User.objects.create_user(username="test_staff_user", is_staff=True)

    def setUp(self):
        self.client = TenantClient(self.tenant)
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

    def test_regenerate_all__many_maps_processed_in_background(self):
        """With more than 5 maps, regeneration is offloaded to a background task
        and the user is warned it is being processed in the background."""
        for i in range(6):
            CytoScape.generate_map(baker.make('quest_manager.Quest'), f"Extra Map {i}")
        self.assertGreater(CytoScape.objects.count(), 5)

        response = self.client.get(reverse('djcytoscape:regenerate_all'), follow=True)
        self.assertTrue(
            any("background" in str(m) for m in response.context['messages']),
            "expected a 'processed in the background' warning message",
        )

    def test_quest_map_interlink__existing_map_renders(self):
        """Interlinking to an object that already initiates a map renders that map."""
        response = self.client.get(reverse(
            'djcytoscape:quest_map_interlink',
            args=[self.map.initial_content_type_id, self.map.initial_object_id, self.map.id],
        ))
        self.assertEqual(response.status_code, 200)
