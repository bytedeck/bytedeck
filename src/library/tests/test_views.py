import uuid
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_exists
from django_tenants.utils import tenant_context
from hackerspace_online.tests.utils import ViewTestUtilsMixin
from library.utils import get_library_schema_name, library_schema_context
from model_bakery import baker
from quest_manager.models import Category, Quest
from siteconfig.models import SiteConfig
from tenant.models import Tenant
from tenant.models import TenantDomain


User = get_user_model()


class LibraryTenantTestCaseMixin(ViewTestUtilsMixin, TenantTestCase):
    library_tenant = None
    library_domain = None

    @classmethod
    def setUpClass(cls):
        # Save current tenant
        _public_tenant = connection.tenant

        super().setUpClass()

        # Need to do this since the setupClass sets the current tenant connection to
        # cls.tenant. We cannot create the library tenant if we are not using the public schema
        # But check first if the library tenant already exists
        cls.library_tenant = Tenant.objects.filter(schema_name=get_library_schema_name()).first()

        if not cls.library_tenant:
            with tenant_context(_public_tenant):
                cls._setup_library_tenant()

    @classmethod
    def get_library_tenant_domain(cls):
        return f'{get_library_schema_name()}.test.com'

    @classmethod
    def _setup_library_tenant(cls):
        # Setup the library tenant
        cls.library_tenant = Tenant(schema_name=get_library_schema_name(), name='Library Tenant')
        cls.library_tenant.save(verbosity=cls.get_verbosity())

        # Setup the domain
        library_domain = cls.get_library_tenant_domain()
        cls.library_domain = TenantDomain(tenant=cls.library_tenant, domain=library_domain)
        cls.library_domain.full_clean()
        cls.library_domain.save()


class QuestLibraryTestsCase(LibraryTenantTestCaseMixin):
    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.sem = SiteConfig.get().active_semester

        self.test_password = 'password'

        with library_schema_context():
            # Create a quest in the library tenant
            self.library_quest = baker.make(Quest)

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student = User.objects.create_user('test_student', password=self.test_password, is_staff=False)

    def test_library_tenant_exists(self):
        """
        Tests that the library tenant is created and exists in the database.
        """
        self.assertIsNotNone(self.library_tenant)
        self.assertTrue(schema_exists(self.library_tenant.schema_name))

    def test_all_library_quest_page_status_codes_for_anonymous(self):
        """
        Tests that the library pages redirect anonymous users to the login page.
        This is important to ensure that only authenticated users can access the library.
        """

        # Should redirect to login for anonymous users
        self.assertRedirectsLogin('library:quest_list')
        self.assertRedirectsLogin('library:import_quest', args=[self.library_quest.import_id])

    def test_all_library_quest_page_status_codes_for_students(self):
        """
        Tests that the library pages return the correct status codes for student users.
        """
        self.client.force_login(self.test_student)

        # Students should not have access to the library pages
        self.assert403('library:quest_list')
        self.assert403('library:import_quest', args=[self.library_quest.import_id])

    def test_all_library_quest_page_status_codes_for_staff(self):
        """
        Tests that the library pages return the correct status codes for staff users.
        """
        self.client.force_login(self.test_teacher)

        # Staff should have access to the library pages
        self.assert200('library:quest_list')
        self.assert200('library:import_quest', args=[self.library_quest.import_id])

    def test_quests_library_list__showing_only_library_quests(self):
        """
        Add test that checks if the library quest list view works and does not list the quests from other tenants
        """

        # Create quests for the non-library tenant
        baker.make(Quest, _quantity=3)
        non_library_quest_count = Quest.objects.get_active().count()

        self.client.force_login(self.test_teacher)
        url = reverse('library:quest_list')
        response = self.client.get(url)

        # Check the request context for the library quests
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(len(response.context['library_quests']), non_library_quest_count)

    def test_import_quest_to_current_deck(self):
        """
        Add tests that check if the import quest to current deck view works.
        2 tests where the quest doesn't import and 1 test of a quest succeeding to import
        """
        self.client.force_login(self.test_teacher)

        # Fail non existing quest
        # This quest fails to import because the import_id doesn't point to a quest

        # Create the url leading to a non-existent quest
        url = reverse('library:import_quest', args=[str(uuid.uuid4())])
        self.assert404URL(url)

        # Fail existing quest
        # This quest fails to import becuase there is already a quest with the same
        # import_id already on the current deck
        # TODO: When we add an overwrite feature, this quest will need to be modified to test that feature

        # Create a quest in the local test schema
        quest = baker.make(Quest)

        # create a quest in the library schema with same import_id
        with library_schema_context():
            library_quest = baker.make(Quest, import_id=quest.import_id)

        url = reverse('library:import_quest', args=[library_quest.import_id])

        # Check that it sends you to the confrimation page with
        self.assertContains(
            self.client.get(url),
            'Your deck already contains a quest with a matching Import ID'
        )

        # Success
        # This quest imports correctly

        # Create a quest in the library schema
        with library_schema_context():
            campaign = baker.make(Category, import_id=uuid.uuid4())
            library_quest = baker.make(
                Quest,
                visible_to_students=True,
                campaign=campaign,
            )

        # sanity check that the library quest does not exist in the local test schema
        with self.assertRaises(Quest.DoesNotExist):
            Quest.objects.get(import_id=library_quest.import_id)

        url = reverse('library:import_quest', args=[library_quest.import_id])

        # Test the confirmation page
        self.assertContains(self.client.get(url), 'Are you sure you want to import this quest into your deck')

        # Make the request to import the quest
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('quests:drafts'))

        # Check that the quest now exists in the local test schema
        quest_qs = Quest.objects.filter(import_id=library_quest.import_id)
        self.assertTrue(quest_qs.exists())

        # Ensure that the newly imported quest is not visible to students
        self.assertFalse(quest_qs.get().visible_to_students)

    def test_side_bar_library_drop_down(self):
        """Checks if library drop down is available when siteconfig.enable_shared_library is true"""
        staff = baker.make(User, is_staff=True)
        self.client.force_login(staff)

        config = SiteConfig.get()

        # if `enable_shared_library=False` then "Quest Library" should not exist
        config.enable_shared_library = False
        config.save()
        response = self.assert200('library:quest_list')
        self.assertNotContains(response, '</i>&nbsp; Quest Library</a>')

        # if `enable_shared_library=True` then "Quest Library" should exist
        config.enable_shared_library = True
        config.save()
        response = self.assert200('library:quest_list')
        self.assertContains(response, '</i>&nbsp; Quest Library</a>')


class CampaignLibraryTestCases(LibraryTenantTestCaseMixin):
    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.sem = SiteConfig.get().active_semester

        self.test_password = 'password'

        with library_schema_context():
            # Create a category in the library tenant
            self.library_category = baker.make(Category)

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student = User.objects.create_user('test_student', password=self.test_password, is_staff=False)

    def test_all_library_category_page_status_codes_for_anonymous(self):
        """
        Tests that the library pages redirect anonymous users to the login page.
        This is important to ensure that only authenticated users can access the library.
        """
        # Category list view
        self.assertRedirectsLogin('library:category_list')
        # Import campaign view
        self.assertRedirectsLogin('library:import_category', args=[self.library_category.import_id])

    def test_all_library_category_page_status_codes_for_students(self):
        """
        Tests that the library pages return the correct status codes for student users.
        """
        self.client.force_login(self.test_student)

        # Students should not have access to the library pages
        self.assert403('library:category_list')
        self.assert403('library:import_category', args=[self.library_category.import_id])

    def test_all_library_category_page_status_codes_for_staff(self):
        """
        Tests that the library pages return the correct status codes for staff users.
        """
        self.client.force_login(self.test_teacher)

        # Staff should have access to the library pages
        self.assert200('library:category_list')
        self.assert200('library:import_category', args=[self.library_category.import_id])

    def test_import_campaign_already_exists(self):
        self.client.force_login(self.test_teacher)
        with library_schema_context():
            # Create a category in the library tenant
            library_category = baker.make(Category, title='Existing Campaign')

        # Create a category in the current tenant with the same import_id
        baker.make(Category, import_id=library_category.import_id, title=library_category.name)

        import_url = reverse('library:import_category', args=[library_category.import_id])

        response = self.client.get(import_url)
        self.assertContains(response, 'Your deck already contains a campaign with a matching name.')

    def test_import_campaign_success(self):
        self.client.force_login(self.test_teacher)
        self.assertEqual(Category.objects.count(), 1)

        with library_schema_context():
            library_campaign = baker.make(Category)
            baker.make(Quest, campaign=library_campaign, _quantity=3)
            self.assertEqual(library_campaign.quest_set.count(), 3)

        import_url = reverse('library:import_category', args=[library_campaign.import_id])

        response = self.client.post(import_url)
        self.assertEqual(response.url, reverse('quests:categories_inactive'))
        self.assertEqual(Category.objects.count(), 2)
        imported_library_campaign = Category.objects.filter(title=library_campaign.name).first()
        self.assertIsNotNone(imported_library_campaign)
        self.assertFalse(imported_library_campaign.active)

        # ensure all 3 quests were imported
        self.assertEqual(imported_library_campaign.quest_set.count(), 3)

        # all imported quests should be inactive for this campaign
        self.assertEqual(imported_library_campaign.quest_set.filter(visible_to_students=False).count(), 3)

    def test_campaigns_library_list__filters_by_current_quests(self):
        """
        Campaigns are only included in the library list if they have at least one
        visible_to_students (published) and unarchived quest.
        """
        self.client.force_login(self.test_teacher)

        with library_schema_context():
            # Make a library campaign that should be visible
            included = baker.make(Category, title='Included Campaign')
            # Make a library campaign that should be excluded because the quest is archived
            excluded_archived = baker.make(Category, title='Archived Only')
            # Make a library campaign that should be excluded because the quest isn't active (draft)
            excluded_invisible = baker.make(Category, title='Invisible Only')

            # Make a current quest on the library and put it in a campaign — should be included
            baker.make(Quest, campaign=included, visible_to_students=True, archived=False)

            # Make an archived quest on the library and put it in a campaign — should not count
            baker.make(Quest, campaign=excluded_archived, visible_to_students=True, archived=True)

            # Make and invisible quest (draft) on the library and put it in a campaign — should not count
            baker.make(Quest, campaign=excluded_invisible, visible_to_students=False, archived=False)

        # Go to the list on the local deck
        response = self.client.get(reverse('library:category_list'))

        self.assertContains(response, included.title)
        self.assertNotContains(response, excluded_archived.title)
        self.assertNotContains(response, excluded_invisible.title)

    def test_campaigns_library_list__excludes_inactive_campaigns(self):
        """
        Inactive campaigns should not appear in the library category list,
        even if they contain visible_to_students (published) and unarchived quests.
        """
        self.client.force_login(self.test_teacher)

        with library_schema_context():
            # Should be shown: active campaign with a visible/unarchived quest
            active_campaign = baker.make(Category, title='Active Campaign', active=True)
            baker.make(Quest, campaign=active_campaign, visible_to_students=True, archived=False)

            # Should be hidden: inactive campaign even though quest is valid
            inactive_campaign = baker.make(Category, title='Inactive Campaign', active=False)
            baker.make(Quest, campaign=inactive_campaign, visible_to_students=True, archived=False)

        response = self.client.get(reverse('library:category_list'))

        self.assertContains(response, active_campaign.title)
        self.assertNotContains(response, inactive_campaign.title)

    def test_import_campaign_view__shows_only_current_quests(self):
        """
        Only current quests (visible_to_students (published) and not archived) should be shown when confirming a campaign import.
        """
        self.client.force_login(self.test_teacher)

        with library_schema_context():
            # Create a campaign with a mix of visible (published), archived, and invisible quests
            campaign = baker.make(Category, title='Visible Campaign')
            # Create a quest that should be displayed
            visible_quest = baker.make(Quest, campaign=campaign, name='Visible', visible_to_students=True, archived=False)
            # Create a quest that should not be displayed (archived)
            archived_quest = baker.make(Quest, campaign=campaign, name='Archived', visible_to_students=True, archived=True)
            # Create a quest that should not be displayed (unpublished/draft)
            invisible_quest = baker.make(Quest, campaign=campaign, name='Invisible', visible_to_students=False, archived=False)

        # Go to the import confirmation page for the campaign
        response = self.client.get(reverse('library:import_category', args=[campaign.import_id]))

        # Should include only the visible (published), non-archived quest
        content = response.content.decode()
        assert visible_quest.name in content
        assert archived_quest.name not in content
        assert invisible_quest.name not in content
