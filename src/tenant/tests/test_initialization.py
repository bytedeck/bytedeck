from django_tenants.test.cases import TenantTestCase
from django.conf import settings
from django.contrib.auth import get_user_model

from badges.models import BadgeRarity
from courses.models import MarkRange
from utilities.models import MenuItem


User = get_user_model()


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

    def test_default_menu_items_created(self):
        self.assertTrue(MenuItem.objects.filter(label="Ranks List").exists())

    def test_admin_created(self):
        """ 
            Check if admin superuser is created upon initialization
        """ 
        username = "admin"
        password = settings.TENANT_DEFAULT_ADMIN_PASSWORD

        user = User.objects.filter(username=username).first()
        self.assertTrue(user is not None)

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

        success = self.client.login(username=username, password=password)
        self.assertTrue(success)

    def test_owner_created(self):
        """ 
            Check if deck_owner is created upon initialization
        """ 
        username = "owner"
        password = settings.TENANT_DEFAULT_OWNER_PASSWORD

        user = User.objects.filter(username=username).first()
        self.assertTrue(user is not None)

        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

        success = self.client.login(username=username, password=password)
        self.assertTrue(success)
