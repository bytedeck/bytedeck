import json
from itertools import cycle

from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker

# from siteconfig.models import SiteConfig
from djcytoscape.models import CytoElement, CytoScape, TempCampaign, TempCampaignNode, clean_JSON
from quest_manager.models import Quest, Category

# from django_tenants.test.client import TenantClient
from hackerspace_online.shell_utils import generate_quests


User = get_user_model()


def generate_real_primary_map():
    """Generate a maps with the initial quests, campaigns, and badges installed via data migrations"""
    welcome_quest = Quest.objects.get(import_id='bee53060-c332-4f75-85e1-6a8f9503ebe1')
    return CytoScape.generate_map(welcome_quest, 'Main')


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

    def test_clean_json_no_braces(self):
        self.assertValidJSON(clean_JSON('"key": true'))

    def test_clean_json_trailing_comma_no_braces(self):
        self.assertValidJSON(clean_JSON('"key": true,'))

    def test_clean_json_trailing_comma_with_braces(self):
        self.assertValidJSON(clean_JSON('{"key": true,}'))

    def test_clean_json_unquoted_key(self):
        self.assertValidJSON(clean_JSON('key: true'))

    def test_clean_json_single_quoted_key(self):
        self.assertValidJSON(clean_JSON('\'key\': true'))

    def test_clean_old_defaults_INIT_OPTIONS(self):
        json_str = """minZoom: 0.5,
            maxZoom: 1.5,
            wheelSensitivity: 0.1,
            zoomingEnabled: false,
            userZoomingEnabled: false,
            autoungrabify: true,
            autounselectify: true,
            """
        self.assertValidJSON(clean_JSON(json_str))

    def test_clean_old_defaults_NODE_STYLES(self):
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

    def test_clean_old_defaults_EDGE_STYLES(self):
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


class CytoElementModelTest(JSONTestCaseMixin, TenantTestCase):
    def setUp(self):
        self.map = generate_real_primary_map()

    def test_object_creation(self):
        self.element = baker.make(CytoElement)
        self.assertIsInstance(self.element, CytoElement)

    def test_json(self):
        """ Should be valid json string, check by deserializing """
        for element in CytoElement.objects.all():
            self.assertValidJSON(element.json())

    def test_json_dict(self):
        for element in CytoElement.objects.all():
            json_dict = element.json_dict()
            self.assertIsInstance(json_dict, dict)
            self.assertValidJSONDict(json_dict)
            self.assertIn('data', json_dict)
            if element.is_node():  # Quests, Campaigns and Badges should have a class
                self.assertIn('classes', json_dict)

    def test_valid_urls(self):
        """ tests if valid urls wont throw ValidationErrors """
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

    def test_invalid_urls(self):
        """ tests if invalid urls throw ValidationErrors """
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


class TempCampaignNodeTest(TenantTestCase):
    def setUp(self):
        self.temp_campaign_node = TempCampaignNode(id_=1)

    def test_object_creation(self):
        self.assertIsInstance(self.temp_campaign_node, TempCampaignNode)
        # this doesn't matter, can be changed
        self.assertEqual(str(self.temp_campaign_node), str(self.temp_campaign_node.id))


class TempCampaignTest(TenantTestCase):
    def setUp(self):
        self.temp_campaign = TempCampaign(parent_node_id=1)

    def test_object_creation(self):
        self.assertIsInstance(self.temp_campaign, TempCampaign)


class CytoScapeModelTest(JSONTestCaseMixin, TenantTestCase):
    def setUp(self):
        self.map = generate_real_primary_map()

    def test_object_creation(self):
        self.assertIsInstance(self.map, CytoScape)
        self.assertEqual(str(self.map), self.map.name)

    def test_object_alphabetical_order(self):
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
        self.assertQuerysetEqual(all_maps, all_maps.order_by('name'))

    def test_generate_map(self):
        quest = baker.make('quest_manager.Quest')
        CytoScape.generate_map(quest, "test")
        self.assertEqual(CytoScape.objects.count(), 2)

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
        newmap = baker.make('djcytoscape.CytoScape')
        self.assertTrue(self.map.is_the_primary_scape)
        self.assertFalse(newmap.is_the_primary_scape)

    def test_save__changes_primary_scape(self):
        newmap = baker.make('djcytoscape.CytoScape')
        self.assertTrue(self.map.is_the_primary_scape)
        self.assertFalse(newmap.is_the_primary_scape)
        newmap.is_the_primary_scape = True
        newmap.save()
        self.assertTrue(newmap.is_the_primary_scape)
        self.map.refresh_from_db()
        self.assertFalse(self.map.is_the_primary_scape)

    def test_elements_dict(self):
        eles_dict = self.map.elements_dict()
        self.assertIsInstance(eles_dict, dict)
        self.assertValidJSONDict(eles_dict)
        self.assertIn('nodes', eles_dict)
        self.assertIn('edges', eles_dict)

    def test_generate_elements_json(self):
        self.assertValidJSON(self.map.generate_elements_json())

    def test_class_styles_list(self):
        styles_list = self.map.class_styles_list()
        self.assertIsInstance(styles_list, list)
        style1 = styles_list[0]
        # list of dictionaries
        self.assertIsInstance(style1, dict)
        self.assertIn('selector', style1)
        self.assertIn('style', style1)

    def test_regenerate(self):
        """Can regenerate without error on a known good map object"""
        self.map.regenerate()

    def test_maps_dont_include_drafts(self):
        """Draft (unpublished) quests should not appear in maps (quest.visible_to_students = False)"""

        # default map json includes quest 6: {'data': {'id': 32, 'label': 'Send your teacher a Message (0)', 'href': '/quests/6/', 'Quest': 6}
        self.assertIn("/quests/6/", self.map.elements_json)

        # Make quest 6 a draft and regenerate the map
        quest_6 = Quest.objects.get(id=6)
        quest_6.visible_to_students = False  # draft/unpublished
        quest_6.save()
        self.map.regenerate()

        # should no longer be in the map
        self.assertNotIn("/quests/6/", self.map.elements_json)

    def test_maps_dont_include_archived_quests(self):
        # default map json includes quest 6: {'data': {'id': 32, 'label': 'Send your teacher a Message (0)', 'href': '/quests/6/', 'Quest': 6}
        self.assertIn("/quests/6/", self.map.elements_json)

        # Archive quest #6 and regenerate the map
        quest_6 = Quest.objects.get(id=6)
        quest_6.archived = True
        quest_6.save()
        self.map.regenerate()

        # should no longer be in the map
        self.assertNotIn("/quests/6/", self.map.elements_json)

    def test_regenerate_deleted_initial_object_throws_exception_and_deletes_map(self):
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

    def test_get_related_maps(self):
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

    def test_get_maps_as_formatted_string(self):
        """ Checks if `get_maps_as_formatted_string` returns the appropriate formatting per length """
        names = [str(x) for x in range(4)]
        scapes = baker.make(CytoScape, name=cycle(names), _quantity=4)

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
