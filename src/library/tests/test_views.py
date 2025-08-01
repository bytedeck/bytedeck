import uuid
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db import connection
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from django_tenants.utils import schema_exists
from django_tenants.utils import tenant_context
from hackerspace_online.tests.utils import ViewTestUtilsMixin
from library.utils import get_library_schema_name, library_schema_context
from library.importer import import_quest_to, import_campaign_to
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
        Tests the quest import view for various scenarios:

        - Case 1: Fails to import a non-existent quest (invalid import_id).
        - Case 2: Fails to import a quest that already exists locally in one of three states:
            a) Published and active
            b) Unpublished
            c) Archived
        In all cases, the import is blocked and a confirmation message is shown.
        - Case 3: Successfully imports a new library quest that does not yet exist on the local deck.
        Verifies:
            - The quest is added to the local schema.
            - It is not immediately visible to students.
            - A success message with a link to the imported quest is displayed.
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

        # Create quests in the local test schema
        # First is a published quest that's not archived
        # Second is a quest that's not published also not archived
        # Third is a quest that's archived
        quest = baker.make(Quest)
        quest_2 = baker.make(Quest, published=False)
        quest_3 = baker.make(Quest, archived=True)

        # create quests in the library schema with same import_ids
        with library_schema_context():
            library_quest = baker.make(Quest, import_id=quest.import_id)
            library_quest_2 = baker.make(Quest, import_id=quest_2.import_id)
            library_quest_3 = baker.make(Quest, import_id=quest_3.import_id)

        # Published quest
        url = reverse('library:import_quest', args=[library_quest.import_id])

        # Check that it sends you to the confrimation page with
        self.assertContains(
            self.client.get(url),
            'Your deck already contains a quest with a matching Import ID'
        )

        # Unpublished quest
        url = reverse('library:import_quest', args=[library_quest_2.import_id])

        # Check that it sends you to the confrimation page with
        self.assertContains(
            self.client.get(url),
            'Your deck already contains a quest with a matching Import ID'
        )

        # Archived quest
        url = reverse('library:import_quest', args=[library_quest_3.import_id])

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
                published=True,
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

        # Ensure that the newly imported quest is not published
        self.assertFalse(quest_qs.get().published)

        # Ensure that the campaign is NOT imported (it's an orphan quest import)
        self.assertFalse(Category.objects.filter(import_id=campaign.import_id).exists())

        # Ensure the success message includes a link to the imported quest
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        message = messages[0].message

        imported_quest = quest_qs.get()
        expected_link = f'<a href="{imported_quest.get_absolute_url()}">{imported_quest.name}</a>'

        self.assertIn(expected_link, message)

    def test_quest_library_list__shows_correct_badge_count(self):
        """
        Ensure the quests tab displays the correct badge count for active quests.
        """
        self.client.force_login(self.test_teacher)
        with library_schema_context():
            # Get the correct quest and campaign count
            quest_count = Quest.objects.get_active().count()
            campaign_count = Category.objects.all_published_with_importable_quests().count()

        url = reverse('library:quest_list')
        response = self.client.get(url)

        # The badges should show the correct quest count
        self.assertContains(response, f'<span class="badge">{quest_count}</span>', html=True)
        self.assertContains(response, f'<span class="badge">{campaign_count}</span>', html=True)

    def test_library_sidebar__shown_if_shared_library_enabled(self):
        """
        The staff sidebar should show the Library link if the shared library is enabled.
        Tests that it doesn't show when shared_library_enabled=False
        Tests that it does show when shared_library_enabled=True
        """
        # Make sure the shared library is initially disabled
        staff = baker.make(User, is_staff=True)
        self.client.force_login(staff)

        config = SiteConfig.get()
        config.enable_shared_library = False
        config.full_clean()
        config.save()

        # Login as staff
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:quest_list'))
        # Checks if the html in the sidebar for library is there (shouldn't be)
        self.assertNotContains(response, 'id="lg-menu-library"')

        # Now enable the shared library
        config.enable_shared_library = True
        config.full_clean()
        config.save()

        # Re-fetch the response after config change
        response = self.client.get(reverse('library:quest_list'))

        # Checks if the html in the sidebar for library is there (should be)
        self.assertContains(response, 'id="lg-menu-library"')


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
        # Category detail view
        self.assertRedirectsLogin('library:category_detail_view', args=[self.library_category.import_id])

    def test_all_library_category_page_status_codes_for_students(self):
        """
        Tests that the library pages return the correct status codes for student users.
        """
        self.client.force_login(self.test_student)

        # Students should not have access to the library pages
        self.assert403('library:category_list')
        self.assert403('library:import_category', args=[self.library_category.import_id])
        self.assert403('library:category_detail_view', args=[self.library_category.import_id])

    def test_all_library_category_page_status_codes_for_staff(self):
        """
        Tests that the library pages return the correct status codes for staff users.
        """
        self.client.force_login(self.test_teacher)

        # Staff should have access to the library pages
        self.assert200('library:category_list')
        self.assert200('library:import_category', args=[self.library_category.import_id])
        self.assert200('library:category_detail_view', args=[self.library_category.import_id])

    def test_import_campaign___already_exists(self):
        self.client.force_login(self.test_teacher)
        with library_schema_context():
            # Create a category in the library tenant
            library_category = baker.make(Category, title='Existing Campaign')

        # Create a category in the current tenant with the same import_id
        baker.make(Category, import_id=library_category.import_id, title=library_category.name)

        import_url = reverse('library:import_category', args=[library_category.import_id])

        response = self.client.get(import_url)
        self.assertContains(response, 'Your deck already contains a campaign with a matching name.')

    def test_import_campaign___success(self):
        self.client.force_login(self.test_teacher)
        self.assertEqual(Category.objects.count(), 1)

        with library_schema_context():
            library_campaign = baker.make(Category)
            baker.make(Quest, published=True, campaign=library_campaign, _quantity=3)
            self.assertEqual(library_campaign.quest_set.count(), 3)

        import_url = reverse('library:import_category', args=[library_campaign.import_id])

        response = self.client.post(import_url)
        self.assertEqual(response.url, reverse('quests:categories_inactive'))
        self.assertEqual(Category.objects.count(), 2)
        imported_library_campaign = Category.objects.filter(title=library_campaign.name).first()
        self.assertIsNotNone(imported_library_campaign)
        self.assertFalse(imported_library_campaign.published)

        # ensure all 3 quests were imported
        self.assertEqual(imported_library_campaign.quest_set.count(), 3)

        # all imported quests should be inactive for this campaign
        self.assertEqual(imported_library_campaign.quest_set.filter(published=False).count(), 3)

        # Assert that the success message includes a link to the imported campaign
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        message = messages[0].message

        expected_link = f'<a href="{imported_library_campaign.get_absolute_url()}">{imported_library_campaign.name}</a>'

        self.assertIn(expected_link, message)

    def test_campaigns_tab__shows_correct_badge_count(self):
        """
        Ensure the campaigns tab displays the correct badge count for active campaigns.
        """
        self.client.force_login(self.test_teacher)
        with library_schema_context():
            # get the correct quest and campiagn count
            quest_count = Quest.objects.get_active().count()
            campaign_count = Category.objects.all_published_with_importable_quests().count()

        url = reverse('library:category_list')
        response = self.client.get(url)

        # The badges should show the correct campaign count
        self.assertContains(response, f'<span class="badge">{quest_count}</span>', html=True)
        self.assertContains(response, f'<span class="badge">{campaign_count}</span>', html=True)

    def test_campaigns_tab__only_shows_library_campaigns(self):
        """
        Ensure the campaigns tab only displays campaigns from the library schema.
        """
        self.client.force_login(self.test_teacher)
        url = reverse('library:category_list')
        response = self.client.get(url)
        with library_schema_context():
            campaign = Category.objects.all_published_with_importable_quests().first()
        # The response should contain the campaign name if one exists
        if campaign:
            self.assertContains(response, campaign.name)

    def test_import_campaign__preserves_local_quest_visibility(self):
        """
        Tests that importing a campaign preserves the local visibility state of existing quests.

        Specifically:
        - Quests imported individually default to unpublished.
        - If a locally imported quest was manually published, re-importing the campaign
        does not overwrite its visibility to unpublished.
        - Quests not previously imported are set to unpublished by default.
        """
        self.client.force_login(self.test_teacher)
        self.assertEqual(Category.objects.count(), 1)

        with library_schema_context():
            library_campaign = baker.make(Category)
            # Create 2 quests in library: both published
            library_quests = baker.make(Quest, campaign=library_campaign, published=True, _quantity=2)

        # Import first quest individually (will be unpublished by default)
        import_quest_to(destination_schema=connection.schema_name, quest_import_id=library_quests[0].import_id)

        # Import second quest individually
        import_quest_to(destination_schema=connection.schema_name, quest_import_id=library_quests[1].import_id)

        # Update the second quest to be published locally
        published_local_quest = Quest.objects.get(import_id=library_quests[1].import_id)
        published_local_quest.published = True
        published_local_quest.full_clean()
        published_local_quest.save()

        # Import full campaign
        import_campaign_to(
            destination_schema=connection.schema_name,
            quest_import_ids=[q.import_id for q in library_quests],
            campaign_import_id=library_campaign.import_id
        )

        # Reload quests from DB
        unpublished_local_quest = Quest.objects.get(import_id=library_quests[0].import_id)
        published_local_quest.refresh_from_db()

        self.assertFalse(unpublished_local_quest.published)
        self.assertTrue(published_local_quest.published)

    def test_campaigns_library_list__filters_by_current_quests(self):
        """
        Campaigns are only included in the library list if they have at least one
        published and unarchived quest.
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
            baker.make(Quest, campaign=included, published=True, archived=False)

            # Make an archived quest on the library and put it in a campaign — should not count
            baker.make(Quest, campaign=excluded_archived, published=True, archived=True)

            # Make and invisible quest (draft) on the library and put it in a campaign — should not count
            baker.make(Quest, campaign=excluded_invisible, published=False, archived=False)

        # Go to the list on the local deck
        response = self.client.get(reverse('library:category_list'))

        self.assertContains(response, included.title)
        self.assertNotContains(response, excluded_archived.title)
        self.assertNotContains(response, excluded_invisible.title)

    def test_campaigns_library_list__excludes_inactive_campaigns(self):
        """
        Inactive campaigns should not appear in the library category list,
        even if they contain published and unarchived quests.
        """
        self.client.force_login(self.test_teacher)

        with library_schema_context():
            # Should be shown: published campaign with a published/unarchived quest
            published_campaign = baker.make(Category, title='published Campaign', published=True)
            baker.make(Quest, campaign=published_campaign, published=True, archived=False)

            # Should be hidden: unpublished campaign even though quest is valid
            unpublished_campaign = baker.make(Category, title='unpublished Campaign', published=False)
            baker.make(Quest, campaign=unpublished_campaign, published=True, archived=False)

        response = self.client.get(reverse('library:category_list'))

        self.assertContains(response, published_campaign.title)
        self.assertNotContains(response, unpublished_campaign.title)

    def test_import_campaign_view__shows_only_current_quests(self):
        """
        Only current quests (published and not archived) should be shown when confirming a campaign import.
        """
        self.client.force_login(self.test_teacher)

        with library_schema_context():
            # Create a campaign with a mix of published, archived, and invisible quests
            campaign = baker.make(Category, title='Visible Campaign')
            # Create a quest that should be displayed
            visible_quest = baker.make(Quest, campaign=campaign, name='published', published=True, archived=False)
            # Create a quest that should not be displayed (archived)
            archived_quest = baker.make(Quest, campaign=campaign, name='ArchivedQuest', published=True, archived=True)
            # Create a quest that should not be displayed (unpublished/draft)
            invisible_quest = baker.make(Quest, campaign=campaign, name='Invisible', published=False, archived=False)

        # Go to the import confirmation page for the campaign
        response = self.client.get(reverse('library:import_category', args=[campaign.import_id]))

        # Should include only the published, non-archived quest
        content = response.content.decode()
        assert visible_quest.name in content
        assert archived_quest.name not in content
        assert invisible_quest.name not in content

    def test_category_detail_view__quest_info(self):
        """
        Test that quest_info in the context contains correct details
        about quests in the campaign.
        """
        self.client.force_login(self.test_teacher)
        with library_schema_context():
            # Add some quests to the library category for this test
            baker.make(Quest, campaign=self.library_category, published=True, archived=False, _quantity=2)

        url = reverse('library:category_detail_view', args=[self.library_category.import_id])
        response = self.client.get(url)
        quest_info = response.context['quest_info']

        # There should be as many quest_info dicts as displayed quests
        self.assertEqual(len(quest_info), len(response.context['category_displayed_quests']))

        # Check keys present in the first quest_info dict
        if quest_info:
            expected_quest_keys = {'id', 'name', 'xp', 'tags', 'published', 'expired'}
            self.assertTrue(expected_quest_keys.issubset(quest_info[0].keys()))

    def test_category_detail_view__404_for_invalid_import_id(self):
        """
        Test that providing a non-existent campaign import_id
        results in a 404 response.
        """
        self.client.force_login(self.test_teacher)
        invalid_id = '00000000-0000-0000-0000-000000000000'
        url = reverse('library:category_detail_view', args=[invalid_id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)


class LibraryOverviewTestsCase(LibraryTenantTestCaseMixin):
    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_password = 'password'

        with library_schema_context():
            # Set up a campaign to test with later
            self.library_campaign = baker.make(Category, published=True)
            # Set up a quest to test with later
            self.library_quest = baker.make(Quest, campaign=self.library_campaign)

        # Need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student = User.objects.create_user('test_student', password=self.test_password, is_staff=False)

    def test_library_overview_redirects_anonymous(self):
        """
        Anonymous users should be redirected to the login page when accessing the library overview.
        """
        response = self.client.get(reverse('library:quest_list'))

        # Expect a 302 redirect
        self.assert302('library:quest_list')

        # Should redirect to login page with next param
        self.assertTrue(response.url.startswith('/accounts/login/'))

    def test_library_overview_for_students(self):
        """
        Authenticated students should receive a 403 Forbidden when trying to access the library
        """
        self.client.force_login(self.test_student)
        self.assert403('library:quest_list')

    def test_library_overview_for_staff_default_tab(self):
        """
        Staff users should see the library overview page with the Quests tab active by default
        """
        self.client.force_login(self.test_teacher)

        # Request the main library overview URL (default tab = Quests)
        response = self.client.get(reverse('library:quest_list'))

        # Page should load successfuly
        self.assert200('library:quest_list')
        self.assertTemplateUsed(response, "library/library_overview.html")

        # The sample quest should be included in the library_quests context
        self.assertIn(self.library_quest, response.context['library_quests'])

        # "Quests" should be the active tab
        self.assertEqual(response.context['tab'], 'quests')

    def test_library_overview__campaigns_tab(self):
        """
        Staff users should see the Campaigns tab content when the library is enabled
        """
        self.client.force_login(self.test_teacher)

        # Go to the Campaigns tab
        response = self.client.get(reverse('library:category_list'))

        # Page should load successfully
        self.assert200('library:category_list')

        # The sample Campaign should be included in the library_categories
        self.assertIn(self.library_campaign, response.context['library_categories'])

        # "Campaigns" should be the active tab
        self.assertEqual(response.context['tab'], 'campaigns')
