import json

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from model_bakery import baker
from unittest.mock import patch

from djcytoscape.models import CytoElement, CytoScape

from profile_manager.models import Profile
from hackerspace_online.tests.utils import ByteDeckTenantTestCase, generate_form_data

User = get_user_model()


class ViewTests(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a teacher, a student, and a map pinned to a dedicated initial quest."""
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

    def test_all_page_status_codes__anonymous(self):
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

    def test_all_page_status_codes__students(self):
        """Students can view maps but are forbidden from edit/regenerate/generate views."""
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

    def test_all_page_status_codes__teachers(self):
        """Teachers can view maps and access the edit/generate views."""
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

    def test_quest_map__map_scripts_are_cache_busted(self):
        """maps.js (and maps-dark.js) are served with a ?v= cache-buster so browsers don't keep
        serving a stale copy that misses map fixes like the campaign name-wrap fix (#1289 / #1937)."""
        self.client.force_login(self.test_student1)
        response = self.client.get(reverse('djcytoscape:quest_map', args=[self.map.id]))
        self.assertContains(response, 'js/maps.js?v=')

        # dark-theme users load an extra script that must be cache-busted too
        self.test_student1.profile.dark_theme = True
        self.test_student1.profile.save()
        response = self.client.get(reverse('djcytoscape:quest_map', args=[self.map.id]))
        self.assertContains(response, 'js/maps-dark.js?v=')

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


class QuestMapAccessAndInterlinkTests(ByteDeckTenantTestCase):
    """Access-control and interlink/generate branches of the map views."""

    @classmethod
    def setUpTestData(cls):
        """A teacher, two students, and a map pinned to a dedicated initial quest."""
        # a teacher must exist before students so profile-creation notifications work
        cls.teacher = User.objects.create_user('cov_teacher', is_staff=True)
        cls.student1 = User.objects.create_user('cov_student1')
        cls.student2 = User.objects.create_user('cov_student2')
        for user in (cls.teacher, cls.student1, cls.student2):
            Profile.objects.get_or_create(user=user)

        cls.quest_ct = ContentType.objects.get(app_label='quest_manager', model='quest')
        # Pin the map's initial object to a dedicated quest (see ViewTests.setUpTestData
        # for why a random baker-filled GFK target is avoided).
        cls.map_quest = baker.make('quest_manager.Quest')
        cls.map = baker.make(
            'djcytoscape.CytoScape',
            initial_content_type=cls.quest_ct,
            initial_object_id=cls.map_quest.id,
        )

    def test_quest_map_personalized__student_cannot_view_another_students_map(self):
        """A non-staff user requesting another user's personalized map gets a 404."""
        self.client.force_login(self.student1)
        response = self.client.get(
            reverse('djcytoscape:quest_map_personalized', args=[self.map.id, self.student2.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_quest_map_interlink__staff_missing_map_offers_generate_form(self):
        """Interlinking to an object that has no map yet, as staff, renders the
        generate-map form (dispatching through ScapeGenerateMap with the initial
        object and parent scape passed through)."""
        unmapped_quest = baker.make('quest_manager.Quest')
        self.client.force_login(self.teacher)
        response = self.client.get(reverse(
            'djcytoscape:quest_map_interlink',
            args=[self.quest_ct.id, unmapped_quest.id, self.map.id],
        ))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'djcytoscape/generate_new_form.html')

    def test_quest_map_interlink__student_missing_map_404(self):
        """Interlinking to an object that has no map yet, as a non-staff user, raises 404."""
        unmapped_quest = baker.make('quest_manager.Quest')
        self.client.force_login(self.student1)
        response = self.client.get(reverse(
            'djcytoscape:quest_map_interlink',
            args=[self.quest_ct.id, unmapped_quest.id, self.map.id],
        ))
        self.assertEqual(response.status_code, 404)

    def test_primary__no_primary_scape_offers_generate_form(self):
        """When maps exist but none is flagged as the primary scape, the primary view
        renders the generate-map form (for staff) rather than a map."""
        # A map exists (so the welcome-quest auto-generation is skipped), but none is primary.
        CytoScape.objects.update(is_the_primary_scape=False)
        self.client.force_login(self.teacher)
        response = self.assert200('djcytoscape:primary')
        self.assertTemplateUsed(response, 'djcytoscape/generate_new_form.html')


class UpdateMapMessageMixinTests(ByteDeckTenantTestCase):
    """UpdateMapMessageMixin adds a 'maps are being updated' message after editing/deleting a
    model that maps depend on (ranks/quests/badges). Its map-auto-update-off path is exercised
    here through a rank delete (RankDelete mixes it in); the message-emitting path is covered by
    the rank/quest/badge suites."""

    def setUp(self):
        """Log in a staff user (the mixin's consumer views require staff)."""
        self.staff = User.objects.create_user('mixin_staff', is_staff=True)
        self.client.force_login(self.staff)

    def test_form_valid__no_map_message_when_auto_update_disabled(self):
        """With SiteConfig.map_auto_update off, deleting a rank skips the related-maps lookup and
        emits no 'maps are being updated' message."""
        from courses.models import Rank
        from siteconfig.models import SiteConfig

        config = SiteConfig.get()
        config.map_auto_update = False
        config.save()

        rank = baker.make(Rank, name="Bronze")
        response = self.client.post(reverse('courses:rank_delete', args=[rank.id]), follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Rank.objects.filter(id=rank.id).exists())
        self.assertFalse(
            any("being updated" in str(m) for m in response.context['messages']),
            "no map-update message should be shown when map_auto_update is off",
        )


class PrimaryViewTests(ByteDeckTenantTestCase):

    def test_primary__generates_initial_map_on_first_view(self):
        """Viewing the primary map for the first time generates the 'Main' map."""
        # shouldn't be any maps from the start
        self.assertFalse(CytoScape.objects.exists())

        # log in anoyone
        anyone = User.objects.create_user('anyone')
        self.client.force_login(anyone)

        # Access the primary map view
        self.assert200('djcytoscape:primary')

        # Should have generated the "Main" map
        self.assertEqual(CytoScape.objects.count(), 1)
        self.assertTrue(CytoScape.objects.filter(name="Main").exists())


class RegenerateViewTests(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Generate the real primary map and a staff user for the regenerate views."""
        from .test_models import generate_real_primary_map

        # regeneration in tests only touches the DB, which is rolled back per test
        cls.map = generate_real_primary_map()
        cls.staff_user = User.objects.create_user(username="test_staff_user", is_staff=True)

    def setUp(self):
        """Set up a tenant client logged in as the staff user."""
        self.client.force_login(self.staff_user)

    def test_regenerate__redirects_to_quest_map(self):
        """Regenerating a good map redirects back to that map's quest_map page."""
        self.assertRedirects(
            response=self.client.get(reverse('djcytoscape:regenerate', args=[self.map.id])),
            expected_url=reverse('djcytoscape:quest_map', args=[self.map.id]),
        )

    def test_regenerate__rebuilds_the_map(self):
        """Regenerating rebuilds the map: its elements are recreated from the current quests and
        badges, the cached json the page renders from is refreshed, and last_regeneration is stamped.

        This is the point of the view, so the elements are wiped first to prove the request put
        them back, rather than asserting on a map that was never disturbed.
        """
        original_node_count = CytoElement.objects.all_for_scape(self.map).nodes().count()
        self.assertGreater(original_node_count, 0, "the fixture map should have nodes to rebuild")
        stale_regeneration = self.map.last_regeneration

        # A map goes stale when the objects it was built from change, so simulate the extreme of
        # that: no elements at all, and a cache that says the map is empty.
        CytoElement.objects.all_for_scape(self.map).delete()
        CytoScape.objects.filter(id=self.map.id).update(elements_json=json.dumps({'nodes': [], 'edges': []}))

        self.client.get(reverse('djcytoscape:regenerate', args=[self.map.id]))

        self.assertEqual(CytoElement.objects.all_for_scape(self.map).nodes().count(), original_node_count)
        rebuilt_map = CytoScape.objects.get(id=self.map.id)
        self.assertEqual(len(json.loads(rebuilt_map.elements_json)['nodes']), original_node_count)
        self.assertGreater(rebuilt_map.last_regeneration, stale_regeneration)

    def test_regenerate__with_deleted_object(self):
        """Regenerating a map whose initial object is gone deletes the map, says so, and redirects
        to the primary map (there is no map page left to send the teacher back to)."""
        bad_map = CytoScape.objects.create(
            name="bad map",
            initial_content_type=ContentType.objects.get(app_label='quest_manager', model='quest'),
            initial_object_id=99999,  # a non-existant object
        )
        response = self.client.get(reverse('djcytoscape:regenerate', args=[bad_map.id]), follow=True)

        self.assertRedirects(response, reverse('djcytoscape:primary'))
        self.assertFalse(CytoScape.objects.filter(id=bad_map.id).exists())
        self.assertTrue(
            any("bad map" in str(m) and "no longer exists" in str(m) for m in response.context['messages']),
            "expected a warning naming the map that was removed",
        )

    def test_regenerate_all__redirects_to_primary(self):
        """Regenerating all maps redirects to the primary map."""
        self.assertRedirects(
            response=self.client.get(reverse('djcytoscape:regenerate_all')),
            expected_url=reverse('djcytoscape:primary'),
        )

    @patch('djcytoscape.views.regenerate_all_maps.apply_async')
    def test_regenerate_all__always_offloads_to_background_task(self, mock_apply_async):
        """Regeneration is always offloaded to the celery task (no inline loop / count
        threshold), and the user is told it's being processed in the background (#2081)."""
        response = self.client.get(reverse('djcytoscape:regenerate_all'), follow=True)

        mock_apply_async.assert_called_once_with(args=[self.staff_user.id], queue='default')
        self.assertTrue(
            any("background" in str(m) for m in response.context['messages']),
            "expected a 'processed in the background' message",
        )

    def test_quest_map_interlink__existing_map_renders(self):
        """Interlinking to an object that already initiates a map renders that map."""
        response = self.client.get(reverse(
            'djcytoscape:quest_map_interlink',
            args=[self.map.initial_content_type_id, self.map.initial_object_id, self.map.id],
        ))
        self.assertEqual(response.status_code, 200)
