from django_tenants.test.cases import TenantTestCase

from unittest.mock import patch
from model_bakery import baker

from djcytoscape.models import CytoScape
from siteconfig.models import SiteConfig
from badges.models import Badge
from quest_manager.models import Quest
from courses.models import Rank
from prerequisites.models import Prereq


@patch('djcytoscape.tasks.regenerate_map.apply_async')
class TestRegenerateMapSignals(TenantTestCase):

    def assert_regenerates_map_on_object_change(self, object_, scape, task):
        """ Helper function that checks if the `regenerate_map` task is triggered
        when saving or deleting an object linked to a Cytoscape map """

        # should regenerate map on save
        object_.save()
        self.assertEqual(task.call_count, 1)
        self.assertEqual(task.call_args.kwargs['args'][0], [scape.id])
        self.assertEqual(CytoScape.objects.get_related_maps(object_).count(), 1)

        # should regenerate map on delete
        # the CytoElement linked also deleted (cascade). Therefore, no related maps
        object_.delete()
        self.assertEqual(task.call_count, 2)
        self.assertEqual(task.call_args.kwargs['args'][0], [scape.id])
        self.assertEqual(CytoScape.objects.get_related_maps(object_).count(), 0)

        # test if task fires if map_auto_update is on
        self.config.map_auto_update = False
        self.config.save()

        object_.save()
        self.assertEqual(task.call_count, 2)

    def setUp(self):
        self.config = SiteConfig.get()

    def tearDown(self):
        self.config.map_auto_update = True
        self.config.save()

    def test_badge_regenerate_related_maps(self, task):
        """ Tests if saving and deleting badge triggers `regenerate_map` task.
        """
        # setup a simple map
        badge = baker.make(Badge)
        scape = CytoScape.generate_map(badge, "Map")

        self.assert_regenerates_map_on_object_change(badge, scape, task)

    def test_quest_regenerate_related_maps(self, task):
        """ Tests if saving and deleting quest triggers `regenerate_map` task.
        """
        # setup a simple map
        quest = baker.make(Quest)
        scape = CytoScape.generate_map(quest, "Map")

        self.assert_regenerates_map_on_object_change(quest, scape, task)

    def test_rank_regenerate_related_maps(self, task):
        """ Tests if saving and deleting rank triggers `regenerate_map` task.
        """
        # setup a simple map
        rank = baker.make(Rank, name="name")  # needs name or generate_map breaks
        scape = CytoScape.generate_map(rank, "Map")

        self.assert_regenerates_map_on_object_change(rank, scape, task)

    def test_prereq_regenerate_related_maps(self, task):
        """ Tests if saving and deleting quest triggers `regenerate_map` task.
        Cant check if `regenerate_map` made new CytoElements. So checking if task args are accurate
        """
        # setup a simple map
        # origin -> quest
        origin = baker.make('quest_manager.quest', name='origin')
        quest = baker.make('quest_manager.quest', name='quest')
        prereq = Prereq.add_simple_prereq(quest, origin)
        scape = CytoScape.generate_map(origin, "Map")

        # should regenerate map on save
        prereq.save()
        self.assertEqual(task.call_count, 1)
        self.assertEqual(task.call_args.kwargs['args'][0], [scape.id])

        # should regenerate map on delete
        prereq.delete()
        self.assertEqual(task.call_count, 2)
        self.assertEqual(task.call_args.kwargs['args'][0], [scape.id])

        # test if task fires if map_auto_update is on
        self.config.map_auto_update = False
        self.config.save()

        prereq.save()
        self.assertEqual(task.call_count, 2)

    def test_prereq_signal_handles_all_registered_parent_models(self, task):
        """Saving a Prereq must not crash the map-regeneration signal for any
        registered prereq model as the parent. Loops through every model that
        implements IsAPrereqMixin — the only models that are supposed to be
        used in a Prereq's generic foreign keys."""
        from django.contrib.contenttypes.models import ContentType
        from prerequisites.models import IsAPrereqMixin

        quest = baker.make(Quest)
        quest_ct = ContentType.objects.get_for_model(Quest)

        for ct in IsAPrereqMixin.all_registered_content_types():
            with self.subTest(parent_model=f'{ct.app_label}.{ct.model}'):
                # A parent id that exists for no object also exercises the
                # signal's DoesNotExist early-return (parent deleted case).
                Prereq.objects.create(
                    parent_content_type=ct,
                    parent_object_id=2147480000,
                    prereq_content_type=quest_ct,
                    prereq_object_id=quest.pk,
                )  # implicitly asserts the post_save signals raise nothing
