import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
# from tenant_schemas.test.client import TenantClient

from quest_manager.models import Quest

# from siteconfig.models import SiteConfig
from djcytoscape.models import CytoStyleClass, CytoStyleSet, CytoElement, TempCampaignNode, TempCampaign, CytoScape, clean_JSON

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


class CytoStyleClassModelTest(TenantTestCase):
    def setUp(self):
        self.style_class = baker.make(CytoStyleClass)

    def test_object_creation(self):
        self.assertIsInstance(self.style_class, CytoStyleClass)
        self.assertEqual(str(self.style_class), self.style_class.name)


class CytoStyleSetModelTest(JSONTestCaseMixin, TenantTestCase):
    def setUp(self):
        self.style_set = baker.make(CytoStyleSet)

    def test_object_creation(self):
        self.assertIsInstance(self.style_set, CytoStyleSet)
        self.assertEqual(str(self.style_set), self.style_set.name)

    def test_get_styles_json_dict(self):
        json_dict = self.style_set.get_styles_json_dict()
        self.assertValidJSONDict(json_dict)
        self.assertIn('style', json_dict)

    def test_default_layout_options_are_valid_json(self):
        self.assertValidJSON(self.style_set.layout_options)

    def test_default_node_styles_are_valid_json(self):
        self.assertValidJSON(self.style_set.node_styles)

    def test_default_edge_styles_are_valid_json(self):
        self.assertValidJSON(self.style_set.edge_styles)

    def test_default_parent_styles_are_valid_json(self):
        self.assertValidJSON(self.style_set.parent_styles)
    
    def test_default_init_options_are_valid_json(self):
        self.assertValidJSON(self.style_set.init_options)

    def test_get_parent_styles_with_bad_json(self):
        """If sorta bad JSON (i.e single or unquotes keys, extra final commas) is provided, 
        it should be cleaned and still parse.  Test using the old default string before JSON was enforced."""

        self.assertValidJSON(self.style_set.get_parent_styles())

        old_parent_styles_default_string = """
            'text-rotation':   '-90deg', 
            'text-halign':     'left', 
            'text-margin-x':   -10, 
            'text-margin-y':   -40,"""
        self.style_set.parent_styles = old_parent_styles_default_string
        self.style_set.save()
       
        self.assertValidJSON(self.style_set.get_parent_styles())

    def test_get_node_styles_with_bad_json(self):
        """If sorta bad JSON (i.e single or unquotes keys, extra final commas) is provided, 
        it should be cleaned and still parse.  Test using the old default string before JSON was enforced."""

        self.assertValidJSON(self.style_set.get_node_styles())

        old_node_styles_default_string = """
            label: 'data(label)', 
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
            'font-size': 12,"""
        self.style_set.node_styles = old_node_styles_default_string
        self.style_set.save()
       
        self.assertValidJSON(self.style_set.get_node_styles())

    def test_get_init_options(self):
        self.assertValidJSON(self.style_set.get_init_options())
        # missing braces and no quotes on key
        dirty_json = "key: true"
        self.style_set.init_options = dirty_json
        self.style_set.save()
        self.assertValidJSON(self.style_set.get_init_options())

    def test_get_layout_options(self):
        self.assertValidJSON(self.style_set.get_layout_json())

    def test_get_classes_json_list(self):
        # Starts with none
        self.assertValidJSONDict(self.style_set.get_classes_json_list())

        # add a couple style classes
        style_class1 = baker.make(CytoStyleClass, name="hidden", styles="'opacity': 0")
        style_class2 = baker.make(CytoStyleClass, name="link", styles="'color': '#2f70a8', 'border-color': '#2f70a8',")
        self.style_set.style_classes.add(style_class1, style_class2)
        classes_list = self.style_set.get_classes_json_list()
        # print(classes_list)
        self.assertValidJSONDict(classes_list)
        self.assertIsInstance(classes_list, list)
        d1 = classes_list[0]
        self.assertIsInstance(d1, dict)
        # Each dictionary in the list should have these two keys:
        self.assertIn('selector', d1)
        self.assertIn('style', d1)

    def test_get_selector_styles_json(self):
        styles = '{"style1": 2, "style2": true}'
        json_str = CytoStyleSet.get_selector_styles_json("test", styles)
        self.assertValidJSON(json_str)

    def test_get_selector_styles_json_dict(self):
        styles = '{"style1": 2, "style2": true}'
        json_dict = CytoStyleSet.get_selector_styles_json_dict("test", styles)
        self.assertIsInstance(json_dict, dict)
        self.assertValidJSONDict(json_dict)
        self.assertIn('selector', json_dict)
        self.assertIn('style', json_dict)


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

    def test_generate_map(self):
        quest = baker.make('quest_manager.Quest')
        CytoScape.generate_map(quest, "test")
        self.assertEqual(CytoScape.objects.count(), 2)

    def test_json(self):
        self.assertValidJSON(self.map.json())

    def test_json_dict(self):
        json_dict = self.map.json_dict()
        self.assertIsInstance(json_dict, dict)
        self.assertValidJSONDict(json_dict)
        self.assertIn('container', json_dict)
        self.assertIn('layout', json_dict)
        self.assertIn('style', json_dict)
        self.assertIn('elements', json_dict)
        self.assertIn('nodes', json_dict['elements'])
        self.assertIn('edges', json_dict['elements'])
