from django_tenants.test.cases import TenantTestCase
from django.conf import settings
from django.contrib.auth import get_user_model

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

    def test_superusers_created(self):
        """ 
            Check if superusers are created, and username/password is correct
        """ 
        User = get_user_model()

        usernames = ['admin', 'owner']
        passwords = [settings.TENANT_DEFAULT_ADMIN_PASSWORD, settings.TENANT_DEFAULT_OWNER_PASSWORD]
        accounts = {usernames[i]: passwords[i] for i in range(len(usernames))}

        for username, password in accounts.items():
            
            # Check if in DB
            user = User.objects.filter(username=username).first()
            self.assertTrue(user is not None)

            # Check if superusers and is_staff
            self.assertTrue(user.is_superuser)
            self.assertTrue(user.is_staff)
            
            # Check if can login
            success = self.client.login(username=username, password=password)
            self.assertTrue(success)
