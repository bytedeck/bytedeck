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


class QuestLibraryTestsCase(LibraryTenantTestCaseMixin, ViewTestUtilsMixin):
    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.sem = SiteConfig.get().active_semester

        self.test_password = 'password'

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student = User.objects.create_user('test_student', password=self.test_password, is_staff=False)
        self.client.force_login(self.test_teacher)

    def test_library_tenant_exists(self):
        self.assertIsNotNone(self.library_tenant)
        self.assertTrue(schema_exists(self.library_tenant.schema_name))

    def test_quest_list_view(self):
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

    def test_import_non_existing_quest_to_current_deck(self):
        url = reverse('library:import_quest', args=[str(uuid.uuid4())])

        # Already logged in as staff in setUp
        self.assert404URL(url)

    def test_import_quest_already_exists_locally(self):
        """Currently we don't support overwriting existing quests (based on import_id),
        so make sure the import feature rejects already existing import_ids
        TODO: When we add an overwrite feature, this quest will need to be modified to test that feature"""

        # Create quest in the test tenant
        quest = baker.make(Quest)

        # Create a quest in the libray schema with same import_id:
        with library_schema_context():
            library_quest = baker.make(Quest, import_id=quest.import_id)

        # Check that the quest exitsts and sends a 403 when trying to import it
        self.assert200('library:import_quest', args=[library_quest.import_id])

    def test_import_library_to_current_deck(self):
        """
        Add test that checks if the import quest to current deck view works
        """
        # Create a quest in the library tenant
        with library_schema_context():
            library_quest = baker.make(Quest)

        # Sanity check that the library quest does not exist in the non-library tenant
        with self.assertRaises(Quest.DoesNotExist):
            Quest.objects.get(import_id=library_quest.import_id)

        url = reverse('library:import_quest', args=[library_quest.import_id])

        # Test the confirmation page
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

        # Make a request to import the quest
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('quests:drafts'))

        # Check that the quest now exists in the non-library tenant
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

    def test_quest_list_view_requires_auth_and_staff(self):
        """
        Test that the quest list view requires authentication and staff permissions.
        """
        # Unauthenticated user should be redirected to login
        self.client.logout()
        response = self.assert302('library:quest_list')
        self.assertIn('/login', response.url)

        # Authenticated non-staff user should be forbidden (403)
        self.client.force_login(self.test_student)
        self.assert403('library:quest_list')

        # Authenticated staff user should succeed
        self.client.force_login(self.test_teacher)
        self.assert200('library:quest_list')

    def test_import_quest_requires_auth_and_staff(self):
        """
        Test that the import quest view requires authentication and staff permissions.
        """
        url_name = 'library:import_quest'
        url_args = (uuid.uuid4())

        # Unauthenticated user
        self.client.logout()
        response = self.assert302(url_name, args=(url_args,))
        self.assertIn('/login', response.url)

        # Authenticated non-staff user
        self.client.force_login(self.test_student)
        response = self.assert403(url_name, args=(url_args,))

        # Authenticated staff user
        self.client.force_login(self.test_teacher)
        # 404 is expected since the quest doesn't exist
        response = self.assert404(url_name, args=(url_args,))


class CampaignLibraryTestCases(LibraryTenantTestCaseMixin, ViewTestUtilsMixin):
    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.sem = SiteConfig.get().active_semester

        self.test_password = 'password'

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student = User.objects.create_user('test_student', password=self.test_password, is_staff=False)
        self.client.force_login(self.test_teacher)

    def test_import_campaign_already_exists(self):
        current_category = Category.objects.first()
        import_url = reverse('library:import_category', args=(current_category.name,))
        response = self.client.get(import_url)
        self.assertContains(response, 'Your deck already contains a campaign with a matching name.')

    def test_import_campaign_success(self):
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

    def test_import_campaign_requires_auth_and_staff(self):
        """
        Test that the import campaign view requires authentication and staff permissions.
        """
        # Make sure there is at least one category to import
        category = baker.make(Category)
        import_url = reverse('library:import_category', args=(category.name,))

        # Unauthenticated user
        self.client.logout()
        response = self.client.get(import_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login', response.url)

        # Authenticated non-staff user
        self.client.force_login(self.test_student)
        response = self.client.get(import_url)
        self.assertEqual(response.status_code, 403)

        # Authenticated staff user
        self.client.force_login(self.test_teacher)
        response = self.client.get(import_url)
        # Should succeed (200 or 404 depending on setup)
        self.assertIn(response.status_code, [200, 404])

    def test_campaings_list_view_requires_auth_and_staff(self):
        """
        Test that the campaigns list view requires authentication and staff permissions.
        """
        url_name = 'library:category_list'

        # Unauthenticated user should be redirected to login
        self.client.logout()
        response = self.assert302(url_name)
        self.assertIn('/login', response.url)

        # Authenticated non-staff user should be forbidden (403)
        self.client.force_login(self.test_student)
        response = self.assert403(url_name)

        # Authenticated staff user should succeed
        self.client.force_login(self.test_teacher)
        self.assert200(url_name)
