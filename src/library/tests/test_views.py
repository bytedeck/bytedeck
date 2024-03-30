from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_exists
from django_tenants.utils import tenant_context
from hackerspace_online.tests.utils import ViewTestUtilsMixin
from library.utils import library_schema_context
from model_bakery import baker
from quest_manager.models import Quest
from siteconfig.models import SiteConfig
from tenant.models import Tenant
from tenant.models import TenantDomain

User = get_user_model()


class QuestLibraryTestsCase(ViewTestUtilsMixin, TenantTestCase):

    @classmethod
    def setUpClass(cls):

        # Save current tenant
        _public_tenant = connection.tenant

        super().setUpClass()

        # Need to do this since the setupClass sets the current tenant connection to
        # cls.tenant. We cannot create the library tenant if we are not using the public schema
        with tenant_context(_public_tenant):
            cls._setup_library_tenant()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

        # Delete the library tenant after all tests are done
        cls.library_tenant.delete(force_drop=True)

    @classmethod
    def get_library_tenant_domain(cls):
        return f'{cls.get_library_schema_name()}.test.com'

    @classmethod
    def get_library_schema_name(cls):
        return f"{apps.get_app_config('library').TENANT_NAME}"

    @classmethod
    def _setup_library_tenant(cls):
        # Setup the library tenant
        cls.library_tenant = Tenant(schema_name=cls.get_library_schema_name(), name='Library Tenant')
        cls.library_tenant.save(verbosity=cls.get_verbosity())

        # Setup the domain
        library_domain = cls.get_library_tenant_domain()
        cls.library_domain = TenantDomain(tenant=cls.library_tenant, domain=library_domain)
        cls.library_domain.save()

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.sem = SiteConfig.get().active_semester

        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)

    def test_library_tenant_exists(self):
        self.assertIsNotNone(self.library_tenant)
        self.assertTrue(schema_exists(self.library_tenant.schema_name))

    def test_library_quest_list_view(self):
        """
        Add test that checks if the library quest list view works and does not list the quests from other tenants
        """

        # Create quests for the non-library tenant
        baker.make(Quest, _quantity=3)
        non_library_quest_count = Quest.objects.get_active().count()

        self.client.force_login(self.test_teacher)
        url = reverse('library_quests:library_quest_list')
        response = self.client.get(url)

        # Check the request context for the library quests
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(len(response.context['library_quests']), non_library_quest_count)

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

        url = reverse('library_quests:import_quest', args=[library_quest.import_id])
        # Make a request to import the quest
        response = self.client.post(url)
        self.assertRedirects(response, reverse('library_quests:library_quest_list'))

        # Check that the quest now exists in the non-library tenant
        quest_qs = Quest.objects.filter(import_id=library_quest.import_id)
        self.assertTrue(quest_qs.exists())

        # Ensure that the newly imported quest is not visible to students
        self.assertFalse(quest_qs.get().visible_to_students)
