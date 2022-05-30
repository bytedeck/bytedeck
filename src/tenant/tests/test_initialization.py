from django_tenants.test.cases import TenantTestCase

from badges.models import BadgeRarity


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
