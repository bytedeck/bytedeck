from django_tenants.test.cases import TenantTestCase

from model_bakery import baker

from djcytoscape.models import CytoScape
from djcytoscape.tasks import regenerate_map


class CytoScapeTaskTests(TenantTestCase):

    def setUp(self):
        self.quest = baker.make('quest_manager.Quest')

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
