import shutil
import tempfile
from unittest.mock import patch

from django_tenants.utils import get_public_schema_name, schema_context, tenant_context
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import override_settings

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from badges.models import Badge, BadgeRarity, BadgeType
from courses.models import Block, Course, Grade, MarkRange, Rank
from quest_manager.models import Category, Quest
from siteconfig.models import SiteConfig
from tenant.initialization import load_initial_tenant_data, set_initial_icons
from tenant.models import Tenant
from utilities.models import MenuItem


User = get_user_model()


class TenantInitializationTest(ByteDeckTenantTestCase):

    def test_initialization__admin_superuser_created(self):
        """ Check if admin superuser is created upon initialization """
        username = "admin"
        password = settings.TENANT_DEFAULT_ADMIN_PASSWORD

        user = User.objects.filter(username=username).first()
        self.assertIsNotNone(user)
        self.assertEqual(user.email, settings.TENANT_DEFAULT_ADMIN_EMAIL)

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)

        success = self.client.login(username=username, password=password)
        self.assertTrue(success)

    def test_initialization__deck_owner_created(self):
        """ Check if deck_owner is created upon initialization """
        username = "owner"
        password = settings.TENANT_DEFAULT_OWNER_PASSWORD

        # user model test
        user = User.objects.filter(username=username).first()
        self.assertIsNotNone(user)

        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

        # profile model test
        profile = user.profile
        self.assertTrue(profile.get_notifications_by_email)
        self.assertTrue(profile.get_announcements_by_email)

        success = self.client.login(username=username, password=password)
        self.assertTrue(success)

    def test_initialization__default_course_created(self):
        """ Initialization script should create a default Course object. """
        self.assertTrue(Course.objects.filter(title="Default").exists())

    def test_initialization__default_block_created(self):
        """ Initialization scripts should create a default Block object. """
        self.assertTrue(Block.objects.filter(name="Default").exists())

    def test_initialization__default_mark_ranges_created(self):
        """ Initialization script should create 3 default MarkRange objects. """
        for name in ["A", "B", "Pass"]:
            self.assertTrue(MarkRange.objects.filter(name=name).exists())

    def test_initialization__default_ranks_created(self):
        """
            Initialization script should create 13 default Rank objects.
            Test shortened for brevity.
        """
        self.assertTrue(Rank.objects.filter(name="Digital Noob").exists())
        self.assertEqual(Rank.objects.count(), 13)

    def test_initialization__default_grades_created(self):
        """ Initialization script should create 5 default Grade objects. """
        for name in ["8", "9", "10", "11", "12"]:
            self.assertTrue(Grade.objects.filter(name=name).exists())

    def test_initialization__default_menu_items_created(self):
        """ Initialization script should create a default MenuItem object. """
        self.assertTrue(MenuItem.objects.filter(label="Ranks List").exists())

    def test_initialization__default_badge_types_created(self):
        """ Initialization script should create 3 default BadgeType objects. """
        self.assertTrue(BadgeType.objects.filter(name="Talent").exists())
        self.assertTrue(BadgeType.objects.filter(name="Award").exists())
        self.assertTrue(BadgeType.objects.filter(name="Team").exists())

    def test_initialization__default_badge_rarities_created(self):
        """ Initialization script should create 6 default BadgeRarity objects. """
        self.assertTrue(BadgeRarity.objects.filter(name="Common").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Uncommon").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Rare").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Epic").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Legendary").exists())
        self.assertTrue(BadgeRarity.objects.filter(name="Mythic").exists())

    def test_initialization__only_default_rarities_created(self):
        """
            Badge rarities shouldn't have overlapping values, and the default rarities cover every percentage value.
            Any additional BadgeRarity objects existing at initialization could cause conflicts.
        """
        self.assertEqual(BadgeRarity.objects.count(), 6)

    def test_initialization__default_badges_created(self):
        """ Initialization script should create 7 default Badge objects. """
        self.assertTrue(Badge.objects.filter(name="Penny").exists())
        self.assertTrue(Badge.objects.filter(name="Nickel").exists())
        self.assertTrue(Badge.objects.filter(name="Dime").exists())
        self.assertTrue(Badge.objects.filter(name="ByteDeck Proficiency").exists())
        self.assertTrue(Badge.objects.filter(name="Red Team").exists())
        self.assertTrue(Badge.objects.filter(name="Green Team").exists())
        self.assertTrue(Badge.objects.filter(name="Blue Team").exists())

    def test_initialization__default_campaign_created(self):
        """ Initialization script should create a default Category (Campaign) object. """
        self.assertTrue(Category.objects.filter(title="Orientation").exists())

    def test_initialization__default_quests_created(self):
        """ Initialization script should create 6 default Quest objects. """
        self.assertTrue(Quest.objects.filter(name="Welcome to ByteDeck!").exists())
        self.assertTrue(Quest.objects.filter(name="ByteDeck Class Contract").exists())
        self.assertTrue(Quest.objects.filter(name="Create an Avatar").exists())
        self.assertTrue(Quest.objects.filter(name="Screenshots").exists())
        self.assertTrue(Quest.objects.filter(name="Who owns your creations?").exists())
        self.assertTrue(Quest.objects.filter(name="Send your teacher a Message").exists())

    def test_initialization__message_quest_notifies_owner(self):
        """ The quest "Send your teacher a Message" should have the deck owner assigned as the specific teacher to notify by default. """
        message_quest = Quest.objects.filter(name="Send your teacher a Message").first()
        owner = User.objects.filter(username="owner", is_staff=True).first()
        self.assertEqual(message_quest.specific_teacher_to_notify, owner)

    def test_create_orientation_campaign__default_tags_created(self):
        """ test if intro tag is properly assigned to
        "Welcome to ByteDeck!" + all quests in the orientation campaign.
        """
        q_intro = Quest.objects.filter(tags__name="intro")
        self.assertEqual(q_intro.count(), 6)
        self.assertTrue(q_intro.filter(name="Welcome to ByteDeck!").exists())
        self.assertTrue(q_intro.filter(name="ByteDeck Class Contract").exists())
        self.assertTrue(q_intro.filter(name="Create an Avatar").exists())
        self.assertTrue(q_intro.filter(name="Screenshots").exists())
        self.assertTrue(q_intro.filter(name="Who owns your creations?").exists())
        self.assertTrue(q_intro.filter(name="Send your teacher a Message").exists())

    def test_create_initial_badges__default_tags_created(self):
        """ test if intro tag is properly assigned to
        "Bytedeck Proficiency"
        """
        b_intro = Badge.objects.filter(tags__name="intro")
        self.assertEqual(b_intro.count(), 1)
        self.assertTrue(b_intro.filter(name="ByteDeck Proficiency").exists())

    def test_initialization__site_config_created(self):
        """ Test that the SiteConfig object exists and the Deck name has expected defaults.
        """
        site_config = SiteConfig.get()
        self.assertIsNotNone(site_config)
        self.assertEqual(site_config.site_name, "My Byte Deck")
        self.assertEqual(site_config.site_name_short, "Deck")


class CreateSiteConfigObjectTest(ByteDeckTenantTestCase):
    """Tests for deriving a new tenant's SiteConfig display names from its deck name."""

    def test_create_site_config__long_deck_name_does_not_overflow(self):
        """A deck name longer than SiteConfig's display fields must not crash
        tenant creation.

        Tenant.name allows up to 62 chars (the Postgres schema-name limit), but
        site_name_short is only 20 (and site_name 50), so a long name previously
        raised "value too long for type character varying(20)" while seeding the
        new tenant. The display names are truncated to fit and stay editable by
        the owner afterwards.
        """
        # A realistic, valid deck name (subdomain) that is longer than the 20-char
        # site_name_short field; creating it fires post_schema_sync, which seeds
        # the new tenant via create_site_config_object. Tenants can only be created
        # from the public schema.
        deck_name = "timberline-secondary-hackerspace"  # 32 chars
        with schema_context(get_public_schema_name()):
            tenant = Tenant(schema_name="timberline_secondary_hackerspace", name=deck_name)
            tenant.save()

        with tenant_context(tenant):
            config = SiteConfig.get()

        expected_title = deck_name.replace("-", " ").title()  # "Timberline Secondary Hackerspace"
        self.assertEqual(config.site_name_short, expected_title[:20])
        self.assertEqual(config.site_name, f"{expected_title} Deck"[:50])


class LoadInitialTenantDataTest(ByteDeckTenantTestCase):
    """Tests for the top-level load_initial_tenant_data entry point."""

    def test_load_initial_tenant_data__public_schema_returns_early(self):
        """Called from the public schema, load_initial_tenant_data returns immediately.

        The public schema is the shared tenant registry, not a deck, so none of the
        per-deck seeding should run there. Patch the first seeding step and assert it
        is never reached.
        """
        with schema_context(get_public_schema_name()):
            with patch("tenant.initialization.create_users") as mock_create_users:
                load_initial_tenant_data()
                mock_create_users.assert_not_called()


class SetInitialIconsTest(ByteDeckTenantTestCase):
    """Tests for set_initial_icons, which uploads a model's icon from a matching static file."""

    @classmethod
    def setUpClass(cls):
        """Isolate MEDIA_ROOT to a temp dir so uploaded icons don't touch the real media store."""
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        cls.addClassCleanup(cls._media_override.disable)
        cls.addClassCleanup(shutil.rmtree, cls._media_root, ignore_errors=True)

    def test_set_initial_icons__uploads_matching_static_icon(self):
        """A badge whose name matches a static icon file gets that icon saved to its ImageField.

        "Dime" has a real static icon at badges/static/badges/img/Dime.png, so
        set_initial_icons should locate it and populate the badge's icon field.
        """
        badge = Badge.objects.get(name="Dime")
        self.assertFalse(badge.icon)  # icons aren't uploaded under the test harness by default

        set_initial_icons([badge])

        badge.refresh_from_db()
        self.assertTrue(badge.icon)
        self.assertTrue(badge.icon.name.endswith(".png"))

    def test_set_initial_icons__missing_icon_does_not_raise(self):
        """When no static icon matches the object's name, set_initial_icons swallows the error.

        finders.find returns None, open() then raises OSError, and the function reports
        the miss instead of crashing tenant creation.
        """
        badge = Badge.objects.create(name="No Such Icon Exists Here", xp=1, badge_type=BadgeType.objects.first())
        self.assertFalse(badge.icon)

        with patch("builtins.print") as mock_print:
            set_initial_icons([badge])

        badge.refresh_from_db()
        self.assertFalse(badge.icon)  # nothing was uploaded
        mock_print.assert_called_once()
        self.assertIn("Couldn't open icon", mock_print.call_args[0][0])
