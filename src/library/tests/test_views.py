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
        Tests the import functionality for quests from the library tenant into the current tenant's deck.
        
        Verifies that importing a non-existent quest returns a 404, importing a quest with a duplicate import ID shows a warning, and successfully importing a new quest adds it to the current deck as not visible to students.
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
            library_quest = baker.make(Quest)

        # Sanity check that the library quest does not exist in the local test schema
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

    def test_quests_tab_shows_correct_badge_count(self):
        """
        Verify that the quests tab displays a badge with the correct count of active quests from the library schema.
        """
        self.client.force_login(self.test_teacher)
        with library_schema_context():
            # Get the correct quest count
            quest_count = Quest.objects.get_active().count()
        url = reverse('library:quest_list')
        response = self.client.get(url)
        # The badge should show the correct quest count
        self.assertContains(response, f'<span class="badge">{quest_count}</span>', html=True)

    def test_quests_tab_only_shows_quests(self):
        """
        Verify that the quests tab displays only quests from the library schema for a logged-in staff user.
        
        This test logs in as a teacher, requests the quest list page, and asserts that the page contains the name of an active quest from the library schema if one exists.
        """
        self.client.force_login(self.test_teacher)
        url = reverse('library:quest_list')
        response = self.client.get(url)
        # Should contain a quest name from the library schema if one exists
        with library_schema_context():
            quest = Quest.objects.get_active().first()
        if quest:
            self.assertContains(response, quest.name)


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
        self.assertRedirectsLogin('library:import_category', args=[self.library_category.name])

    def test_all_library_category_page_status_codes_for_students(self):
        """
        Tests that the library pages return the correct status codes for student users.
        """
        self.client.force_login(self.test_student)

        # Students should not have access to the library pages
        self.assert403('library:category_list')
        self.assert403('library:import_category', args=[self.library_category.name])

    def test_all_library_category_page_status_codes_for_staff(self):
        """
        Tests that the library pages return the correct status codes for staff users.
        """
        self.client.force_login(self.test_teacher)

        # Staff should have access to the library pages
        self.assert200('library:category_list')
        self.assert200('library:import_category', args=[self.library_category.name])

    def test_import_campaign_already_exists(self):
        self.client.force_login(self.test_teacher)
        with library_schema_context():
            library_campaign = baker.make(Category)
        local_campaign = baker.make(Category, title=library_campaign.name)
        import_url = reverse('library:import_category', args=(local_campaign.name,))
        response = self.client.get(import_url)
        self.assertContains(response, 'Your deck already contains a campaign with a matching name.')

    def test_import_campaign_success(self):
        """
        Tests successful import of a campaign and its quests from the library tenant, ensuring the imported campaign and quests are inactive and correctly associated.
        """
        self.client.force_login(self.test_teacher)
        self.assertEqual(Category.objects.count(), 1)

        with library_schema_context():
            library_campaign = baker.make(Category)
            baker.make(Quest, campaign=library_campaign, _quantity=3)
            self.assertEqual(library_campaign.quest_set.count(), 3)

        import_url = reverse('library:import_category', args=(library_campaign.name,))
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

    def test_campaigns_tab_shows_correct_badge_count(self):
        """
        Verify that the campaigns tab displays a badge with the correct count of active campaigns from the library schema.
        """
        self.client.force_login(self.test_teacher)
        with library_schema_context():
            # get the correct campiagn count
            campaign_count = Category.objects.filter(active=True).count()
        url = reverse('library:category_list')
        response = self.client.get(url)
        # The badge should show the correct campaign count
        self.assertContains(response, f'<span class="badge">{campaign_count}</span>', html=True)

    def test_campaigns_tab_only_shows_campaigns(self):
        """
        Verify that the campaigns tab displays only active campaigns from the library schema.
        
        The test logs in as a staff user, requests the campaign list page, and asserts that the page contains the name of an active campaign from the library schema if one exists.
        """
        self.client.force_login(self.test_teacher)
        url = reverse('library:category_list')
        response = self.client.get(url)
        with library_schema_context():
            campaign = Category.objects.filter(active=True).first()
        # The response should contain the campaign name if one exists
        if campaign:
            self.assertContains(response, campaign.name)
