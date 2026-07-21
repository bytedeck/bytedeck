import json
from collections import defaultdict
from itertools import cycle

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase

from model_bakery import baker

# from siteconfig.models import SiteConfig
from djcytoscape.models import CytoElement, CytoScape, TempCampaign, TempCampaignNode, clean_JSON
from prerequisites.models import Prereq
from quest_manager.models import Quest, Category

# from django_tenants.test.client import TenantClient
from hackerspace_online.shell_utils import generate_quests
from hackerspace_online.tests.utils import ByteDeckTenantTestCase


User = get_user_model()


def generate_real_primary_map():
    """Generate a maps with the initial quests, campaigns, and badges installed via data migrations"""
    welcome_quest = Quest.objects.get(import_id='bee53060-c332-4f75-85e1-6a8f9503ebe1')
    return CytoScape.generate_map(welcome_quest, 'Main')


def bake_scape(**kwargs):
    """``baker.make`` a CytoScape pointed at a real Quest initial object.

    CytoScape.initial_content_type is a non-nullable ForeignKey(ContentType) with a
    uniqueness constraint on (initial_content_type, initial_object_id). Bare
    ``baker.make(CytoScape)`` would give it a random, dangling initial object, so
    these tests pin it to a freshly-created Quest instead.
    """
    kwargs.setdefault('initial_content_type', ContentType.objects.get_for_model(Quest))
    kwargs.setdefault('initial_object_id', baker.make('quest_manager.Quest').id)
    return baker.make(CytoScape, **kwargs)


class JSONTestCaseMixin:

    def assertValidJSON(self, str):
        """Tests that a string is valid JSON and returns the JSON deserialized as a python object via json.loads
        """
        try:
            return json.loads(str)
        except TypeError:
            self.fail(f"Can't deserialize this JSON string: \n {str}")

    def assertValidJSONDict(self, json_dict):
        """Tests that a python dictionary can be serialized into JSON via json.dumps
        """
        try:
            return json.dumps(json_dict)
        except json.JSONDecodeError:
            self.fail(f"Can't serialize this dict into JSON: \n {json_dict}")


class CleanJSONTest(JSONTestCaseMixin, SimpleTestCase):
    """ All tests for the method: def clean_JSON(dirty_json_str): """

    def test_clean_JSON__no_braces(self):
        """A brace-less key/value string is cleaned into valid JSON."""
        self.assertValidJSON(clean_JSON('"key": true'))

    def test_clean_JSON__trailing_comma_no_braces(self):
        """A brace-less string with a trailing comma is cleaned into valid JSON."""
        self.assertValidJSON(clean_JSON('"key": true,'))

    def test_clean_JSON__trailing_comma_with_braces(self):
        """A braced object with a trailing comma is cleaned into valid JSON."""
        self.assertValidJSON(clean_JSON('{"key": true,}'))

    def test_clean_JSON__unquoted_key(self):
        """An unquoted key is quoted so the result is valid JSON."""
        self.assertValidJSON(clean_JSON('key: true'))

    def test_clean_JSON__single_quoted_key(self):
        """A single-quoted key is normalised to double quotes for valid JSON."""
        self.assertValidJSON(clean_JSON('\'key\': true'))

    def test_clean_JSON__old_defaults_init_options(self):
        """The legacy INIT_OPTIONS defaults block is cleaned into valid JSON."""
        json_str = """minZoom: 0.5,
            maxZoom: 1.5,
            wheelSensitivity: 0.1,
            zoomingEnabled: false,
            userZoomingEnabled: false,
            autoungrabify: true,
            autounselectify: true,
            """
        self.assertValidJSON(clean_JSON(json_str))

    def test_clean_JSON__old_defaults_node_styles(self):
        """The legacy NODE_STYLES defaults block is cleaned into valid JSON."""
        json_str = """label: 'data(label)',
            'text-valign':   'center', 'text-halign': 'right',
            'text-margin-x': '-155',
            'text-wrap': 'wrap',
            'text-max-width': 150,
            'width':         180,
            'background-fit':'contain',
            'shape':         'roundrectangle',
            'background-opacity': 0,
            'background-position-x': 0,
            'height': 24,
            'border-width':  1,
            'padding-right': 5, 'padding-left':5, 'padding-top':5, 'padding-bottom':5,
            'text-events':   'yes',
            'font-size': 12,
            """
        self.assertValidJSON(clean_JSON(json_str))

    def test_clean_JSON__old_defaults_edge_styles(self):
        """The legacy EDGE_STYLES defaults block is cleaned into valid JSON."""
        json_str = """'width': 1,
            'curve-style':   'bezier',
            'line-color':    'black',
            'line-style':    'solid',
            'target-arrow-shape': 'triangle-backcurve',
            'target-arrow-color':'black',
            'text-rotation': 'autorotate',
            'label':         'data(label)',
            """
        self.assertValidJSON(clean_JSON(json_str))


class CytoElementModelTest(JSONTestCaseMixin, ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Generate the real primary map to populate CytoElement rows for the tests."""
        cls.map = generate_real_primary_map()

    def test_object_creation__is_cytoelement_instance(self):
        """A baked object is a CytoElement instance."""
        self.element = baker.make(CytoElement)
        self.assertIsInstance(self.element, CytoElement)

    def test_json__is_valid_json_string(self):
        """Each element's json() returns a deserializable JSON string."""
        for element in CytoElement.objects.all():
            self.assertValidJSON(element.json())

    def test_json_dict__is_valid_dict_with_data(self):
        """Each element's json_dict() is a serializable dict with a 'data' key (and 'classes' for nodes)."""
        for element in CytoElement.objects.all():
            json_dict = element.json_dict()
            self.assertIsInstance(json_dict, dict)
            self.assertValidJSONDict(json_dict)
            self.assertIn('data', json_dict)
            if element.is_node():  # Quests, Campaigns and Badges should have a class
                self.assertIn('classes', json_dict)

    def test_full_clean__valid_urls(self):
        """Valid href URLs pass full_clean without raising ValidationError."""
        element = baker.make(CytoElement)
        valid_urls = [
            '/',
            '/quests/',
            '/quests/1/2/',
            'http://example.com',

            # what we will typically encounter for CytoElement href
            '/quests/1/',
            '/badges/1/',
            '/ranks/',
            '/maps/2/1/1/',
            '/maps/2/1/',
            '/maps/2/',
        ]
        for url in valid_urls:
            try:
                element.href = url
                element.full_clean()
            except ValidationError:
                self.fail(f"{url} is not a valid URL")

    def test_full_clean__invalid_urls(self):
        """Invalid href URLs raise ValidationError during full_clean."""
        element = baker.make(CytoElement)
        invalid_urls = [
            ' ',  # space
            '/ ',  # space
            '/quests /',  # space
            'quests-quests/',  # -
        ]
        for url in invalid_urls:
            with self.assertRaises(ValidationError):
                element.href = url
                element.full_clean()

    def test_str__node_shows_id_and_label(self):
        """A NODE element stringifies as '<id>: <label>'."""
        node = baker.make(CytoElement, scape=self.map, group=CytoElement.NODES, label="Hello")
        self.assertEqual(str(node), f"{node.id}: Hello")

    def test_str__edge_shows_source_and_target(self):
        """An EDGE element stringifies as '<id>: <source id>-><target id>'."""
        src = baker.make(CytoElement, scape=self.map, group=CytoElement.NODES)
        tgt = baker.make(CytoElement, scape=self.map, group=CytoElement.NODES)
        edge = baker.make(CytoElement, scape=self.map, group=CytoElement.EDGES, data_source=src, data_target=tgt)
        self.assertEqual(str(edge), f"{edge.id}: {src.id}->{tgt.id}")

    def test_json_dict__edge_includes_min_len_when_above_default(self):
        """An edge whose min_len differs from the default (1) exposes it as 'minLen' in its data."""
        src = baker.make(CytoElement, scape=self.map, group=CytoElement.NODES)
        tgt = baker.make(CytoElement, scape=self.map, group=CytoElement.NODES)
        edge = baker.make(
            CytoElement, scape=self.map, group=CytoElement.EDGES,
            data_source=src, data_target=tgt, min_len=3,
        )
        self.assertEqual(edge.json_dict()["data"]["minLen"], "3")

    def test_get_selector_styles_json_dict__returns_none_without_styles(self):
        """With no style string, the helper returns None (there's nothing to emit)."""
        self.assertIsNone(CytoElement.get_selector_styles_json_dict("#1", ""))
        self.assertIsNone(CytoElement.get_selector_styles_json_dict("#1", None))


class TempCampaignNodeTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Build a TempCampaignNode instance for the tests."""
        cls.temp_campaign_node = TempCampaignNode(id_=1)

    def test_object_creation__is_instance_and_str_is_id(self):
        """A TempCampaignNode is created and its string form is its id."""
        self.assertIsInstance(self.temp_campaign_node, TempCampaignNode)
        # this doesn't matter, can be changed
        self.assertEqual(str(self.temp_campaign_node), str(self.temp_campaign_node.id))


class TempCampaignTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Build a TempCampaign instance for the tests."""
        cls.temp_campaign = TempCampaign(parent_node_id=1)

    def test_object_creation__is_instance(self):
        """A baked TempCampaign is a TempCampaign instance."""
        self.assertIsInstance(self.temp_campaign, TempCampaign)

    def test_str__no_children(self):
        """A campaign with no nodes reports that it has no children."""
        self.assertIn("No children", str(TempCampaign(parent_node_id=1)))

    def test_str__with_children(self):
        """A campaign's string lists its parent id and each child node."""
        tc = TempCampaign(parent_node_id=1)
        tc.add_node(node_id=10, prereq_node_id=None)
        tc.add_node(node_id=11, prereq_node_id=None)
        rendered = str(tc)
        self.assertIn("Parent: 1", rendered)
        self.assertIn("Child:10", rendered)
        self.assertIn("Child:11", rendered)

    def test_add_node__existing_id_appends_prereq(self):
        """Re-adding an existing node id appends the new prereq instead of duplicating the node."""
        tc = TempCampaign(parent_node_id=1)
        tc.add_node(node_id=10, prereq_node_id=100)
        tc.add_node(node_id=10, prereq_node_id=101)
        self.assertEqual(len(tc.nodes), 1)
        self.assertEqual(tc.get_node(10).prereq_node_ids, [100, 101])

    def test_add_campaign_reliant__tracks_node_id(self):
        """Nodes directly reliant on the campaign are tracked in campaign_reliant_node_ids."""
        tc = TempCampaign(parent_node_id=1)
        tc.add_campaign_reliant(reliant_node_id=42)
        self.assertEqual(tc.campaign_reliant_node_ids, [42])

    def test_has_internal_reliant__true_only_for_internal_reliant(self):
        """has_internal_reliant is True only when an internal node is a reliant of the given node."""
        tc = TempCampaign(parent_node_id=1)
        tc.add_node(node_id=10, prereq_node_id=None)
        tc.add_node(node_id=11, prereq_node_id=None)
        # node 11 (internal) relies on node 10 -> internal reliant
        tc.add_reliant(node_id=10, reliant_node_id=11)
        self.assertTrue(tc.has_internal_reliant(tc.get_node(10)))
        # node 11's reliant is an external id -> not internal
        tc.add_reliant(node_id=11, reliant_node_id=999)
        self.assertFalse(tc.has_internal_reliant(tc.get_node(11)))

    def test_is_non_sequential__always_false_due_to_is_true_comparison(self):
        """is_non_sequential runs over a campaign whose nodes share a common prereq.

        Note: the method body compares a *list* with ``is True`` (``get_common_prereq_node_ids()
        is True``), so it currently always returns False regardless of the campaign's shape.
        This test pins that current behavior; it should be revisited if the comparison is fixed.
        """
        tc = TempCampaign(parent_node_id=1)
        tc.add_node(node_id=10, prereq_node_id=100)
        tc.add_node(node_id=11, prereq_node_id=100)
        # Both nodes share prereq 100, so get_common_prereq_node_ids() is non-empty...
        self.assertEqual(tc.get_common_prereq_node_ids(), [100])
        # ...but `[...] is True` is False, so is_non_sequential() returns False today.
        self.assertFalse(tc.is_non_sequential())


class CytoManagerTests(ByteDeckTenantTestCase):
    """Tests for the CytoElement/CytoScape manager helpers (random-node pickers and lookups)."""

    @classmethod
    def setUpTestData(cls):
        """Generate the real primary map to give the manager helpers nodes to work with."""
        cls.map = generate_real_primary_map()

    def test_get_random_node__returns_node_in_scape(self):
        """get_random_node returns a NODE element belonging to the given scape."""
        node = CytoElement.objects.get_random_node(self.map)
        self.assertEqual(node.scape_id, self.map.id)
        self.assertEqual(node.group, CytoElement.NODES)

    def test_get_random_node_triangular_distribution__returns_node_in_scape(self):
        """The triangular-distribution picker also returns a node from the scape."""
        node = CytoElement.objects.get_random_node_triangular_distribution(self.map)
        self.assertEqual(node.scape_id, self.map.id)
        self.assertEqual(node.group, CytoElement.NODES)

    def test_get_map_for_init__missing_then_found(self):
        """get_map_for_init returns None when no map initiates the object, else that map."""
        quest = baker.make('quest_manager.Quest')
        self.assertIsNone(CytoScape.objects.get_map_for_init(quest))

        scape = CytoScape.generate_map(quest, "Quest Map")
        found = CytoScape.objects.get_map_for_init(quest)
        self.assertEqual(found, scape)
        self.assertEqual(found.initial_object_id, quest.id)

    def test_all_for_campaign__returns_only_nodes_parented_to_that_campaign(self):
        """all_for_campaign returns the scape's nodes whose data_parent is the given campaign node."""
        scape = bake_scape()
        campaign_node = baker.make(CytoElement, scape=scape, group=CytoElement.NODES)
        child = baker.make(CytoElement, scape=scape, group=CytoElement.NODES, data_parent=campaign_node)
        unparented = baker.make(CytoElement, scape=scape, group=CytoElement.NODES)

        result = CytoElement.objects.all_for_campaign(scape, campaign_node)

        self.assertIn(child, result)
        self.assertNotIn(unparented, result)
        self.assertNotIn(campaign_node, result)


class CytoScapeModelTest(JSONTestCaseMixin, ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Generate the real primary map as a shared fixture for the scape tests."""
        # tests that regenerate/mutate the map only touch the DB, which is rolled
        # back per test, and self.map is a per-test deep copy — safe class-level fixture
        cls.map = generate_real_primary_map()

    def test_object_creation__is_instance_and_str_is_name(self):
        """A generated map is a CytoScape whose string form is its name."""
        self.assertIsInstance(self.map, CytoScape)
        self.assertEqual(str(self.map), self.map.name)

    def test_object_alphabetical_order__maps_ordered_by_name(self):
        """
        Map objects are ordered alphabetically at the model level to ensure
        proper sorting consistently sitewide.
        """
        # Need to generate three different quests here so that the maps are
        # created with no error
        questA = baker.make('quest_manager.Quest')
        questB = baker.make('quest_manager.Quest')
        questC = baker.make('quest_manager.Quest')
        # Generate maps out of order to ensure they're sorted by name
        CytoScape.generate_map(questB, "B")
        CytoScape.generate_map(questC, "C")
        CytoScape.generate_map(questA, "A")
        all_maps = CytoScape.objects.all()  # Main is included in this list
        # A queryset created from all objects is ordered correctly by default
        self.assertQuerySetEqual(all_maps, all_maps.order_by('name'))

    def test_generate_map__creates_new_scape(self):
        """generate_map creates a new CytoScape for the given initial object."""
        quest = baker.make('quest_manager.Quest')
        CytoScape.generate_map(quest, "test")
        self.assertEqual(CytoScape.objects.count(), 2)

    def test_generate_map__transition_node_for_tilde_quest(self):
        """A reliant quest whose label starts with '~' is turned into a transition
        (child-map link) node: is_transition_node() detects it and
        convert_to_transition_node() flags the node and restyles it."""
        start = baker.make('quest_manager.Quest', name="Start Quest")
        # A '~'-prefixed name marks a map break -> transition node (autobreak on by default).
        transition = baker.make('quest_manager.Quest', name="~Continue in the next map")
        transition.add_simple_prereqs([start])  # transition relies on start

        scape = CytoScape.generate_map(start, "Transition Map")

        node = CytoElement.objects.get(
            scape=scape, selector_id=CytoElement.generate_selector_id(transition),
        )
        self.assertTrue(node.is_transition)
        self.assertIn("child-map", node.classes)

    def test_is_transition_node__autobreak_off_returns_false(self):
        """With autobreak disabled, no node is treated as a transition node."""
        scape = self.map
        scape.autobreak = False
        any_node = scape.cytoelement_set.filter(group=CytoElement.NODES).first()
        self.assertFalse(scape.is_transition_node(any_node))

    def test_generate_map__long_name_xp(self):
        """
        objects with long names + xp should be truncated correctly during map generation to avoid raising a DataError where labels are too long:

        Exception Type: DataError at /maps/all/regenerate/
        Exception Value: value too long for type character varying(50)
        """
        # Create a quest with name length 50 and xp 10000000 to ensure dynamic label truncation catches all potential cases
        # testing for badges, etc. not needed as truncation only checks for xp attribute, not object type
        # xp_can_be_entered_by_students appends a single "+" character to label, so testing with it verifies it is caught as well
        quest = baker.make('quest_manager.Quest', name="____Sample Quest Name with 50 Character Length____", xp=10000000,
                           xp_can_be_entered_by_students=True)

        # Generate map with created quest and assert generation is successful (object count increased from default 1 to 2)
        CytoScape.generate_map(quest, "test")
        self.assertEqual(CytoScape.objects.count(), 2)

    def test_save__sets_first_scape_as_primary(self):
        """The first-created map is primary; a second map saved afterwards is not."""
        newmap = bake_scape()
        self.assertTrue(self.map.is_the_primary_scape)
        self.assertFalse(newmap.is_the_primary_scape)

    def test_save__changes_primary_scape(self):
        """Flagging a second map primary and saving demotes the previous primary map."""
        newmap = bake_scape()
        self.assertTrue(self.map.is_the_primary_scape)
        self.assertFalse(newmap.is_the_primary_scape)
        newmap.is_the_primary_scape = True
        newmap.save()
        self.assertTrue(newmap.is_the_primary_scape)
        self.map.refresh_from_db()
        self.assertFalse(self.map.is_the_primary_scape)

    def test_save__setting_primary_when_none_exists_is_handled(self):
        """Saving a map as primary when no current primary exists doesn't error.

        save() demotes the existing primary map, but guards the lookup with
        CytoScape.DoesNotExist for the edge case where none is currently flagged.
        """
        bake_scape()  # a second map exists, so the count-based first-map branch is skipped
        CytoScape.objects.update(is_the_primary_scape=False)
        self.assertFalse(CytoScape.objects.filter(is_the_primary_scape=True).exists())

        new_primary = bake_scape(is_the_primary_scape=True)

        new_primary.refresh_from_db()
        self.assertTrue(new_primary.is_the_primary_scape)

    def test_elements_dict__has_nodes_and_edges(self):
        """elements_dict returns a serializable dict containing 'nodes' and 'edges'."""
        eles_dict = self.map.elements_dict()
        self.assertIsInstance(eles_dict, dict)
        self.assertValidJSONDict(eles_dict)
        self.assertIn('nodes', eles_dict)
        self.assertIn('edges', eles_dict)

    def test_generate_elements_json__is_valid_json(self):
        """generate_elements_json returns a valid JSON string."""
        self.assertValidJSON(self.map.generate_elements_json())

    def test_class_styles_list__returns_selector_style_dicts(self):
        """class_styles_list returns dicts each carrying a 'selector' and 'style'."""
        styles_list = self.map.class_styles_list()
        self.assertIsInstance(styles_list, list)
        style1 = styles_list[0]
        # list of dictionaries
        self.assertIsInstance(style1, dict)
        self.assertIn('selector', style1)
        self.assertIn('style', style1)

    def test_regenerate__no_error_on_good_map(self):
        """Can regenerate without error on a known good map object"""
        self.map.regenerate()

    def test_cytoelement_ordering__is_a_total_order(self):
        """CytoElement.Meta.ordering must end with the unique `id` tiebreaker so element
        emission is deterministic. Without it, sibling elements (same group and data_parent —
        e.g. every top-level node, whose data_parent is NULL) come back in whatever order
        Postgres returns, which shifts as regenerate() churns rows. Because dagre lays out
        same-rank nodes by their input order, that made the map toggle between layouts on each
        regeneration (issue #1977).
        """
        self.assertEqual(CytoElement._meta.ordering[-1], 'id')

    def test_elements_dict__nodes_in_ascending_id_order_within_parent_groups(self):
        """The emitted map JSON must list nodes in a deterministic order: within each compound
        (campaign) parent — and among the top-level nodes — siblings come out in ascending id,
        i.e. creation order. A stable emission order in means a stable dagre layout out (#1977).
        """
        ids_by_parent = defaultdict(list)
        for node in self.map.elements_dict()['nodes']:
            ids_by_parent[node['data'].get('parent')].append(node['data']['id'])

        # sanity: the real primary map has more than one node to order
        self.assertGreater(sum(len(ids) for ids in ids_by_parent.values()), 1)
        for parent, ids in ids_by_parent.items():
            self.assertEqual(ids, sorted(ids), msg=f"nodes under parent {parent} are not id-ordered")

    def test_regenerate__produces_stable_node_order(self):
        """Regenerating a map must yield the same left-to-right node order every time so the
        rendered layout is deterministic (issue #1977). Node ids change on each regeneration but
        their labels don't, so we compare the ordered sequence of labels across two regenerations.
        """
        def ordered_labels():
            return [node['data'].get('label') for node in self.map.elements_dict()['nodes']]

        before = ordered_labels()
        self.map.regenerate()
        after = ordered_labels()
        self.assertEqual(before, after)

    def test_regenerate__excludes_draft_quests(self):
        """Draft unpublished quests should not appear in maps"""

        # default map json includes quest 6: {'data': {'id': 32, 'label': 'Send your teacher a Message (0)', 'href': '/quests/6/', 'Quest': 6}
        self.assertIn("/quests/6/", self.map.elements_json)

        # Make quest 6 a draft and regenerate the map
        quest_6 = Quest.objects.get(id=6)
        quest_6.published = False  # draft/unpublished
        quest_6.save()
        self.map.regenerate()

        # should no longer be in the map
        self.assertNotIn("/quests/6/", self.map.elements_json)

    def test_regenerate__excludes_archived_quests(self):
        """Archived quests should not appear in maps after regeneration."""
        # default map json includes quest 6: {'data': {'id': 32, 'label': 'Send your teacher a Message (0)', 'href': '/quests/6/', 'Quest': 6}
        self.assertIn("/quests/6/", self.map.elements_json)

        # Archive quest #6 and regenerate the map
        quest_6 = Quest.objects.get(id=6)
        quest_6.archived = True
        quest_6.full_clean()
        quest_6.save()
        self.map.regenerate()

        # should no longer be in the map
        self.assertNotIn("/quests/6/", self.map.elements_json)

    def test_regenerate__deleted_initial_object_throws_and_deletes_map(self):
        """when regenerating a map that has had its initial object deleted, remove it and raise error."""
        bad_map = CytoScape.objects.create(
            name="bad map",
            initial_content_type=ContentType.objects.get(app_label='quest_manager', model='quest'),
            initial_object_id=99999,  # a non-existant object
        )

        with self.assertRaises(bad_map.InitialObjectDoesNotExist):
            bad_map.regenerate()

        # should have been deleted at this point
        self.assertFalse(CytoScape.objects.filter(name="bad map").exists())

    def test_get_related_maps__counts_maps_per_quest(self):
        """ Check if CytoScape.objects.get_related_maps returns the correct maps per quest.
        """

        # create 3 categories
        # exclude orientation as its linked with the main map
        generate_quests(5, 3, quiet=True)
        categories = Category.objects.exclude(title='Orientation').order_by('id')
        self.assertEqual(categories.count(), 3)

        # order category quest by id. Because when generating map:
        # min(id) = source node
        # max(id) = leaf node
        c1, c2, c3 = list(categories)
        c1_quests = c1.current_quests().order_by('id')
        c2_quests = c2.current_quests().order_by('id')
        c3_quests = c3.current_quests().order_by('id')

        # no map as base case
        self.no_maps = baker.make(Quest)

        # quest exists only on one map
        self.one_map = baker.make(Quest)
        self.one_map.add_simple_prereqs([c1_quests.last()])

        # quests exist on every map
        self.all_maps = baker.make(Quest)
        self.all_maps.add_simple_prereqs([
            c1_quests.last(),
            c2_quests.last(),
            c3_quests.last(),
        ])

        # generate maps from categories
        CytoScape.generate_map(c1_quests.first(), "Map 1")
        CytoScape.generate_map(c2_quests.first(), "Map 2")
        CytoScape.generate_map(c3_quests.first(), "Map 3")

        # test if get_related_maps get correct
        self.assertEqual(CytoScape.objects.get_related_maps(self.no_maps).count(), 0)
        self.assertEqual(CytoScape.objects.get_related_maps(self.one_map).count(), 1)
        self.assertEqual(CytoScape.objects.get_related_maps(self.all_maps).count(), 3)

    def test_get_maps_as_formatted_string__formats_by_length(self):
        """ Checks if `get_maps_as_formatted_string` returns the appropriate formatting per length """
        names = [str(x) for x in range(4)]
        # Each scape needs a distinct real initial object: (initial_content_type,
        # initial_object_id) is unique-constrained, so cycle 4 fresh Quest ids.
        quest_ids = [baker.make('quest_manager.Quest').id for _ in range(4)]
        scapes = baker.make(
            CytoScape, name=cycle(names),
            initial_content_type=ContentType.objects.get_for_model(Quest),
            initial_object_id=cycle(quest_ids),
            _quantity=4,
        )

        # since baker returns a list with `_quantity` > 1
        # we have to convert it to a queryset
        scape_ids = [s.id for s in scapes]
        scapes = CytoScape.objects.filter(id__in=scape_ids)

        scape_0 = f'<a href="/maps/{scapes[0].id}/">0</a>'
        scape_1 = f'<a href="/maps/{scapes[1].id}/">1</a>'
        scape_2 = f'<a href="/maps/{scapes[2].id}/">2</a>'
        scape_3 = f'<a href="/maps/{scapes[3].id}/">3</a>'

        expected_results = [
            None,
            f'{scape_0}',
            f'{scape_0} and {scape_1}',
            f'{scape_0}, {scape_1}, and {scape_2}',
            f'{scape_0}, {scape_1}, {scape_2}, and {scape_3}',
        ]
        for index, expected in enumerate(expected_results):
            result = scapes[0:index].get_maps_as_formatted_string()
            self.assertEqual(result, expected)


class CampaignMapOrderTest(ByteDeckTenantTestCase):
    """Campaigns are placed left-to-right on the quest map in Category.map_order (issue #1977,
    the ordering half). dagre orders same-rank nodes by crossing-minimization and ignores input
    order, so the order can't be imposed in the emitted JSON — instead every node carries a
    ``campaignOrder`` (its campaign's map_order) and maps.js repositions the campaign columns to
    match after layout. These tests cover the server side of that contract: that the right
    ``campaignOrder`` is emitted on every node. Two campaigns branch off a common Start quest so
    they render as siblings.
    """

    @classmethod
    def setUpTestData(cls):
        """Two campaigns (A, B), each with one member quest that has the shared Start quest as a
        prerequisite, so both campaigns render as siblings branching off Start.
        """
        cls.start = baker.make(Quest, name="Start")
        # "A-quest" sorts before "B-quest", so campaign A's node is created first (lower id) —
        # i.e. A is left of B by default, before any map_order is applied.
        cls.camp_a = baker.make(Category, title="AAA Campaign")
        cls.camp_b = baker.make(Category, title="BBB Campaign")
        cls.qa = baker.make(Quest, name="A-quest", campaign=cls.camp_a)
        cls.qb = baker.make(Quest, name="B-quest", campaign=cls.camp_b)
        Prereq.add_simple_prereq(cls.qa, cls.start)
        Prereq.add_simple_prereq(cls.qb, cls.start)

    def _emit(self):
        """Regenerate the map and return its elements dict."""
        return CytoScape.generate_map(self.start, "order-test").elements_dict()

    @staticmethod
    def _index_by_category(nodes, category_id):
        """Position of a campaign's compound node in the emitted node list."""
        return next(i for i, n in enumerate(nodes) if n['data'].get('Category') == category_id)

    @staticmethod
    def _campaign_order(nodes, *, category_id=None, quest_id=None):
        """The campaignOrder emitted on a campaign's compound node or on a quest's node."""
        for n in nodes:
            if category_id is not None and n['data'].get('Category') == category_id:
                return n['data']['campaignOrder']
            if quest_id is not None and n['data'].get('Quest') == quest_id:
                return n['data']['campaignOrder']
        raise AssertionError("node not found")

    def test_add_to_campaign__campaign_node_links_back_to_its_category(self):
        """The compound campaign node carries selector_id 'Category: <pk>' so the map can look up
        the campaign's map_order — and json_dict surfaces it as a `Category` data attribute.
        """
        scape = CytoScape.generate_map(self.start, "order-test")
        node = scape.cytoelement_set.get(classes='campaign', label__startswith='AAA')
        self.assertEqual(node.selector_id, f'Category: {self.camp_a.id}')

    def test_elements_dict__default_map_order_keeps_deterministic_node_order(self):
        """With map_order left at its default 0, nodes are emitted in ascending-id order (A's
        campaign node before B's), preserving the deterministic layout from issue #2012 so maps
        where nobody set an order are unchanged.
        """
        nodes = self._emit()['nodes']
        self.assertLess(
            self._index_by_category(nodes, self.camp_a.id),
            self._index_by_category(nodes, self.camp_b.id),
        )

    def test_elements_dict__emits_campaign_order_on_every_node(self):
        """Every node carries `campaignOrder` = its campaign's map_order; member quests inherit
        their campaign's, and campaign-less nodes (the shared Start quest) default to 0. This is
        the value maps.js reads to order the campaign columns left-to-right — the array position
        no longer encodes the order (dagre would ignore it), so the data attribute must.
        """
        self.camp_a.map_order = 5
        self.camp_a.full_clean()
        self.camp_a.save()
        self.camp_b.map_order = 1
        self.camp_b.full_clean()
        self.camp_b.save()

        nodes = self._emit()['nodes']

        # campaign compound nodes carry their own map_order
        self.assertEqual(self._campaign_order(nodes, category_id=self.camp_a.id), 5)
        self.assertEqual(self._campaign_order(nodes, category_id=self.camp_b.id), 1)
        # member quests inherit their campaign's map_order
        self.assertEqual(self._campaign_order(nodes, quest_id=self.qa.id), 5)
        self.assertEqual(self._campaign_order(nodes, quest_id=self.qb.id), 1)
        # the campaign-less Start quest defaults to 0
        self.assertEqual(self._campaign_order(nodes, quest_id=self.start.id), 0)
