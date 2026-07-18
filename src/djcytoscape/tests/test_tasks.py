from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from model_bakery import baker

from djcytoscape.models import CytoScape
from djcytoscape.tasks import regenerate_all_maps, regenerate_map
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from notifications.models import Notification

User = get_user_model()


class CytoScapeTaskTests(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        cls.quest = baker.make('quest_manager.Quest')

    def _bad_map(self):
        """A map whose initial object no longer exists (initial_object_id points at nothing)."""
        quest_ct = ContentType.objects.get(app_label='quest_manager', model='quest')
        return CytoScape.objects.create(
            name="Bad Map", initial_content_type=quest_ct, initial_object_id=999999,
        )

    def test_regenerate_all_maps(self):
        """regenerate_all_maps regenerates valid maps, deletes maps whose initial
        object is gone, and notifies the requesting user of the failure and of the
        overall completion."""
        requesting_user = baker.make(User, is_staff=True)
        good_map = CytoScape.generate_map(self.quest, "Good Map")
        bad_map = self._bad_map()

        notes_before = Notification.objects.all_for_user(requesting_user).count()
        regenerate_all_maps.apply(args=[requesting_user.id], queue='default').get()

        # the valid map survives; the broken one is removed
        self.assertTrue(CytoScape.objects.filter(id=good_map.id).exists())
        self.assertFalse(CytoScape.objects.filter(id=bad_map.id).exists())

        # one "failed to regenerate" notice for the bad map + one "completed" notice
        notes_after = Notification.objects.all_for_user(requesting_user).count()
        self.assertEqual(notes_after - notes_before, 2)

    def test_regenerate_map__deleted_initial_object_is_swallowed(self):
        """regenerate_map silently drops a map whose initial object no longer exists (no raise)."""
        bad_map = self._bad_map()
        regenerate_map.apply(args=[[bad_map.id]], queue='default').get()
        self.assertFalse(CytoScape.objects.filter(id=bad_map.id).exists())

    def test_regenerate_map(self):
        """ tests if regenerate map task runs successfully """
        map_origins = baker.make('quest_manager.Quest', _quantity=3)

        # create map for each origin (3 maps)
        for count, origin in enumerate(map_origins):
            CytoScape.generate_map(origin, f"Map {count}")

        self.quest.add_simple_prereqs(map_origins)

        # since map hasnt been updated, quest should not be related to any maps
        self.assertEqual(CytoScape.objects.get_related_maps(self.quest).count(), 0)

        # run tasks in the background and wait for it to finish
        # have to use apply because we cant wait for `apply_async` because disabled backend
        # cant run task.successful() because celery is not set up for result retrieval (ie. will cause attribute error: DisabledBackend)
        map_ids = list(CytoScape.objects.order_by('-id')[:3].values_list('id', flat=True))
        task = regenerate_map.apply(args=[map_ids], queue='default')
        task.get()

        # should be 3 as self.quest got linked to 3 maps
        self.assertEqual(CytoScape.objects.get_related_maps(self.quest).count(), 3)
