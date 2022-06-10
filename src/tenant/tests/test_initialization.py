from django_tenants.test.cases import TenantTestCase

from badges.models import BadgeRarity
from courses.models import MarkRange


class TenantInitializationTest(TenantTestCase):

    def test_default_badge_rarities_created(self):
        """When a new tenant is created, the initialization script should create 6 default BadgeRarity objects."""
        self.assertTrue(BadgeRarity.objects.filter(name="Common").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Uncommon").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Rare").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Epic").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Legendary").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Mythic").exists())
    
    def test_only_default_rarities_created(self):
        self.assertEqual(BadgeRarity.objects.count(), 6)

    def test_default_mark_ranges_created(self):
        """ 
            When a new tenant is created, the initialization script should create 3 default Markrange objects.
        """ 
        for name in ["A", "B", "Pass"]:
            self.assertTrue(MarkRange.objects.filter(name=name).exists())
