from django_tenants.test.cases import TenantTestCase
from django.conf import settings
from django.contrib.auth import get_user_model

from badges.models import Badge, BadgeRarity, BadgeType
from courses.models import Block, Course, Grade, MarkRange, Rank
from quest_manager.models import Category, Quest
from utilities.models import MenuItem


User = get_user_model()


class TenantInitializationTest(TenantTestCase):

    def test_admin_created(self):
        """ Check if admin superuser is created upon initialization """
        username = "admin"
        password = settings.TENANT_DEFAULT_ADMIN_PASSWORD

        user = User.objects.filter(username=username).first()
        self.assertTrue(user is not None)
        self.assertEqual(user.email, settings.TENANT_DEFAULT_ADMIN_EMAIL)

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

        success = self.client.login(username=username, password=password)
        self.assertTrue(success)

    def test_owner_created(self):
        """ Check if deck_owner is created upon initialization """
        username = "owner"
        password = settings.TENANT_DEFAULT_OWNER_PASSWORD

        # user model test
        user = User.objects.filter(username=username).first()
        self.assertTrue(user is not None)

        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

        # profile model test
        profile = user.profile
        self.assertTrue(profile.get_notifications_by_email)
        self.assertTrue(profile.get_announcements_by_email)

        success = self.client.login(username=username, password=password)
        self.assertTrue(success)

    def test_default_course_created(self):
        """ Initialization script should create a default Course object. """
        self.assertTrue(Course.objects.filter(title="Default").exists())

    def test_default_block_created(self):
        """ Initialization scripts should create a default Block object. """
        self.assertTrue(Block.objects.filter(name="Default").exists())

    def test_default_mark_ranges_created(self):
        """ Initialization script should create 3 default MarkRange objects. """
        for name in ["A", "B", "Pass"]:
            self.assertTrue(MarkRange.objects.filter(name=name).exists())

    def test_default_ranks_created(self):
        """
            Initialization script should create 13 default Rank objects.
            Test shortened for brevity.
        """
        self.assertTrue(Rank.objects.filter(name="Digital Noob").exists())
        self.assertEqual(Rank.objects.count(), 13)

    def test_default_grades_created(self):
        """ Initialization script should create 5 default Grade objects. """
        for name in ["8", "9", "10", "11", "12"]:
            self.assertTrue(Grade.objects.filter(name=name).exists())

    def test_default_menu_items_created(self):
        """ Initialization script should create a default MenuItem object. """
        self.assertTrue(MenuItem.objects.filter(label="Ranks List").exists())

    def test_default_badge_types_created(self):
        """ Initialization script should create 3 default BadgeType objects. """
        self.assertTrue(BadgeType.objects.filter(name="Talent").exists())
        self.assertTrue(BadgeType.objects.filter(name="Award").exists())
        self.assertTrue(BadgeType.objects.filter(name="Team").exists())

    def test_default_badge_rarities_created(self):
        """ Initialization script should create 6 default BadgeRarity objects. """
        self.assertTrue(BadgeRarity.objects.filter(name="Common").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Uncommon").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Rare").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Epic").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Legendary").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Mythic").exists())

    def test_only_default_rarities_created(self):
        """
            Badge rarities shouldn't have overlapping values, and the default rarities cover every percentage value.
            Any additional BadgeRarity objects existing at initialization could cause conflicts.
        """
        self.assertEqual(BadgeRarity.objects.count(), 6)

    def test_default_badges_created(self):
        """ Initialization script should create 7 default Badge objects. """
        self.assertTrue(Badge.objects.filter(name="Penny").exists())
        self.assertTrue(Badge.objects.filter(name="Nickel").exists())
        self.assertTrue(Badge.objects.filter(name="Dime").exists())
        self.assertTrue(Badge.objects.filter(name="ByteDeck Proficiency").exists())
        self.assertTrue(Badge.objects.filter(name="Red Team").exists())
        self.assertTrue(Badge.objects.filter(name="Green Team").exists())
        self.assertTrue(Badge.objects.filter(name="Blue Team").exists())

    def test_default_badge_icons(self):
        """
            Empty because Django tests involving static files are prone to breakage.
            Come back to this once testing static files is made clearer.
        """

    def test_default_campaign_created(self):
        """ Initialization script should create a default Category (Campaign) object. """
        self.assertTrue(Category.objects.filter(title="Orientation").exists())

    def test_default_quests_created(self):
        """ Initialization script should create 6 default Quest objects. """
        self.assertTrue(Quest.objects.filter(name="Welcome to ByteDeck!").exists())
        self.assertTrue(Quest.objects.filter(name="ByteDeck Class Contract").exists())
        self.assertTrue(Quest.objects.filter(name="Create an Avatar").exists())
        self.assertTrue(Quest.objects.filter(name="Screenshots").exists())
        self.assertTrue(Quest.objects.filter(name="Who owns your creations?").exists())
        self.assertTrue(Quest.objects.filter(name="Send your teacher a Message").exists())

    def test_default_quest_icons(self):
        """
            Empty because Django tests involving static files are prone to breakage.
            Come back to this once testing static files is made clearer.
        """

    def test_default_message_quest_notifies_owner(self):
        """ The quest "Send your teacher a Message" should have the deck owner assigned as the specific teacher to notify by default. """
        message_quest = Quest.objects.filter(name="Send your teacher a Message").first()
        owner = User.objects.filter(username="owner", is_staff=True).first()
        self.assertEqual(message_quest.specific_teacher_to_notify, owner)

    def test_site_config_created(self):
        """ Test that the SiteConfig object exists and the Deck name has expected defaults.
        """
        from siteconfig.models import SiteConfig
        site_config = SiteConfig.get()
        self.assertTrue(site_config is not None)
        self.assertEqual(site_config.site_name, "My Byte Deck")
        self.assertEqual(site_config.site_name_short, "Deck")
