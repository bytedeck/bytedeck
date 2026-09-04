from unittest.mock import patch

from django.core.cache import cache

from model_bakery import baker

from djcytoscape.models import CytoScape
from djcytoscape.tasks import MAP_REGENERATION_DELAY
from djcytoscape.tests.utils import simulate_regeneration_starting
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig
from badges.models import Badge
from quest_manager.models import Quest
from courses.models import Rank
from prerequisites.models import Prereq


@patch('djcytoscape.tasks.regenerate_map.apply_async')
class TestRegenerateMapSignals(ByteDeckTenantTestCase):

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
        simulate_regeneration_starting(scape.id)
        object_.delete()
        self.assertEqual(task.call_count, 2)
        self.assertEqual(task.call_args.kwargs['args'][0], [scape.id])
        self.assertEqual(CytoScape.objects.get_related_maps(object_).count(), 0)

        # test if task fires if map_auto_update is on
        self.config.map_auto_update = False
        self.config.save()

        # clear the marker first, so the flag is the only thing that can be keeping
        # this save off the queue
        simulate_regeneration_starting(scape.id)
        object_.save()
        self.assertEqual(task.call_count, 2)

    def setUp(self):
        """Grab the tenant's SiteConfig singleton for toggling map_auto_update."""
        self.config = SiteConfig.get()

    def tearDown(self):
        """Restore map_auto_update to its enabled default after each test."""
        self.config.map_auto_update = True
        self.config.save()

    def test_regenerate_related_maps__badge(self, task):
        """ Tests if saving and deleting badge triggers `regenerate_map` task.
        """
        # setup a simple map
        badge = baker.make(Badge)
        scape = CytoScape.generate_map(badge, "Map")

        self.assert_regenerates_map_on_object_change(badge, scape, task)

    def test_regenerate_related_maps__quest(self, task):
        """ Tests if saving and deleting quest triggers `regenerate_map` task.
        """
        # setup a simple map
        quest = baker.make(Quest)
        scape = CytoScape.generate_map(quest, "Map")

        self.assert_regenerates_map_on_object_change(quest, scape, task)

    def test_regenerate_related_maps__rank(self, task):
        """ Tests if saving and deleting rank triggers `regenerate_map` task.
        """
        # setup a simple map
        rank = baker.make(Rank, name="name")  # needs name or generate_map breaks
        scape = CytoScape.generate_map(rank, "Map")

        self.assert_regenerates_map_on_object_change(rank, scape, task)

    def test_regenerate_related_maps__prereq(self, task):
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
        simulate_regeneration_starting(scape.id)
        prereq.delete()
        self.assertEqual(task.call_count, 2)
        self.assertEqual(task.call_args.kwargs['args'][0], [scape.id])

        # test if task fires if map_auto_update is on
        self.config.map_auto_update = False
        self.config.save()

        # clear the marker first, so the flag is the only thing that can be keeping
        # this save off the queue
        simulate_regeneration_starting(scape.id)
        prereq.save()
        self.assertEqual(task.call_count, 2)

    def test_regenerate_related_maps__a_run_of_saves_queues_one_regeneration(self, task):
        """A run of saves touching one map queues a single regeneration, not one apiece.

        Editing a quest with a few prereqs fires this signal several times over, and a
        bulk operation such as a library import fires it a great many times. Each of
        those used to queue a full rebuild of the same map, and since they take the
        map's row in turn they then ran one after another, each throwing away the last
        one's work (#2658).
        """
        quest = baker.make(Quest)
        scape = CytoScape.generate_map(quest, "Map")

        for _ in range(5):
            quest.save()

        self.assertEqual(task.call_count, 1)
        self.assertEqual(task.call_args.kwargs['args'][0], [scape.id])

        # the wait is what makes collapsing them sound: the one rebuild that runs reads
        # the database after the rest of the run of saves has landed
        self.assertEqual(task.call_args.kwargs['countdown'], MAP_REGENERATION_DELAY)

    def test_regenerate_related_maps__a_save_after_the_regeneration_starts_queues_another(self, task):
        """A save landing once the queued regeneration has begun gets one of its own.

        That rebuild may already have read past the change, so folding this save into it
        would drop the edit rather than merely defer it: the map would stay as it was
        until something else happened to be saved.
        """
        quest = baker.make(Quest)
        scape = CytoScape.generate_map(quest, "Map")

        quest.save()
        self.assertEqual(task.call_count, 1)

        simulate_regeneration_starting(scape.id)

        quest.save()
        self.assertEqual(task.call_count, 2)
        self.assertEqual(task.call_args.kwargs['args'][0], [scape.id])

    def test_regenerate_related_maps__collapses_per_map_not_per_save(self, task):
        """Each map is collapsed on its own: one still pending doesn't hold up another.

        A quest appears on as many maps as reference it, and they are rebuilt by
        separate tasks that finish at different times, so a save has to be able to queue
        a rebuild of one of them while another's is still waiting.
        """
        origin_a = baker.make(Quest, name='origin a')
        origin_b = baker.make(Quest, name='origin b')
        quest = baker.make(Quest, name='quest')
        quest.add_simple_prereqs([origin_a, origin_b])

        map_a = CytoScape.generate_map(origin_a, "Map A")
        map_b = CytoScape.generate_map(origin_b, "Map B")

        # start counting from the built fixture rather than from the saves that built it
        task.reset_mock()
        cache.clear()

        quest.save()
        self.assertEqual(task.call_count, 1)
        self.assertEqual(sorted(task.call_args.kwargs['args'][0]), sorted([map_a.id, map_b.id]))

        simulate_regeneration_starting(map_a.id)

        quest.save()
        self.assertEqual(task.call_count, 2)
        self.assertEqual(task.call_args.kwargs['args'][0], [map_a.id], "map B's pending regeneration should still cover it")

    def test_prereq_signal__handles_all_registered_parent_models(self, task):
        """Saving a Prereq must not crash the map-regeneration signal for any
        registered prereq model as the parent. Loops through every model that
        implements IsAPrereqMixin, the only models that are supposed to be
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
