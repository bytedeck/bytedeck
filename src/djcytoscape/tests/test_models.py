from django.contrib.auth import get_user_model

from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
# from tenant_schemas.test.client import TenantClient

# from siteconfig.models import SiteConfig
from djcytoscape.models import CytoStyleClass, CytoStyleSet, CytoElement, TempCampaignNode, TempCampaign, CytoScape

User = get_user_model()


class CytoStyleClassModelTest(TenantTestCase):
    def setUp(self):
        self.style_class = baker.make(CytoStyleClass)

    def test_object_creation(self):
        self.assertIsInstance(self.style_class, CytoStyleClass)
        self.assertEqual(str(self.style_class), self.style_class.name)


class CytoStyleSetModelTest(TenantTestCase):
    def setUp(self):
        self.style_set = baker.make(CytoStyleSet)

    def test_object_creation(self):
        self.assertIsInstance(self.style_set, CytoStyleSet)
        self.assertEqual(str(self.style_set), self.style_set.name)


class CytoElementModelTest(TenantTestCase):
    def setUp(self):
        self.element = baker.make(CytoElement)

    def test_object_creation(self):
        self.assertIsInstance(self.element, CytoElement)


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


class CytoScapeModelTest(TenantTestCase):
    def setUp(self):
        self.map = baker.make(CytoScape)

    def test_object_creation(self):
        self.assertIsInstance(self.map, CytoScape)
        self.assertEqual(str(self.map), self.map.name)

    def test_generate_map(self):
        quest = baker.make('quest_manager.Quest')
        CytoScape.generate_map(quest, "test")
