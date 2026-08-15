import uuid
from copy import deepcopy
from datetime import date
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection
from django.http import Http404
from django.test import RequestFactory
from django.urls import reverse
from django_tenants.utils import get_public_schema_name, schema_exists
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from library.utils import get_library_schema_name, library_schema_context
from library.models import ContentOrigin
from library.views import LibraryQuestListView, shared_library_enabled_view, viewer_is_library_staff
from library.importer import import_quest_to, import_campaign_to
from library.exporter import (
    build_library_clone_name,
    clone_quests_into_library,
    export_campaign_and_copy_quests,
    export_campaign_to_library,
    export_quest_to_library,
)
from model_bakery import baker
from notifications.models import Notification
from quest_manager.models import Category, CommonData, Quest
from siteconfig.models import SiteConfig
from tenant.models import Tenant
from tenant.models import TenantDomain


User = get_user_model()

# What the browser sends when the sharer ticks the licence checkbox on an export
# confirmation page. The push is refused without it (#2366).
AGREED_LICENCE = {'agree_license': 'on'}


class LibraryTenantTestCaseMixin(ByteDeckTenantTestCase):
    library_tenant = None
    library_domain = None

    @classmethod
    def setUpClass(cls):
        # Create (or reuse) the library tenant BEFORE super().setUpClass(): the
        # ByteDeckTenantTestCase base enters Django's class-wide atomic block at
        # the end of its setUpClass, and the library tenant must be committed
        # outside that transaction so it survives the class-level rollback and
        # can be reused by every test class that needs it. At this point the
        # connection is still on the public schema, where Tenant rows live.
        cls.library_tenant = Tenant.objects.filter(schema_name=get_library_schema_name()).first()

        if not cls.library_tenant:
            cls._setup_library_tenant()

        super().setUpClass()

    def setUp(self):
        """Turn the Shared Library on for the deck under test.

        Every test in this module exercises a deck that has opted into the feature.
        The opted-out case has its own class (`SharedLibraryDisabledTests`), so the
        default here is "enabled" rather than SiteConfig's off-by-default.
        """
        super().setUp()
        config = SiteConfig.get()
        config.enable_shared_library = True
        config.save()

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
    @classmethod
    def setUpTestData(cls):
        """Create library and local quests plus teacher/student users."""
        with library_schema_context():
            # Create a quest in the library tenant
            cls.shared_quest = baker.make(Quest)
            cls.library_quest = baker.make(Quest)

        cls.local_quest = baker.make(Quest)
        baker.make(Quest, import_id=cls.shared_quest.import_id)

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student = User.objects.create_user('test_student', is_staff=False)

    def setUp(self):
        """Set up the site config and active semester."""
        super().setUp()
        self.config = SiteConfig.get()
        self.sem = SiteConfig.get().active_semester

    def test_library_tenant__exists(self):
        """
        Tests that the library tenant is created and exists in the database.
        """
        self.assertIsNotNone(self.library_tenant)
        self.assertTrue(schema_exists(self.library_tenant.schema_name))

    def test_all_library_quest_page_status_codes__for_anonymous(self):
        """
        Tests that the library pages redirect anonymous users to the login page.
        This is important to ensure that only authenticated users can access the library.
        """

        # Should redirect to login for anonymous users
        self.assertRedirectsLogin('library:quest_list')
        self.assertRedirectsLogin('library:import_quest', args=[self.library_quest.import_id])

    def test_all_library_quest_page_status_codes__for_students(self):
        """
        Tests that the library pages return the correct status codes for student users.
        """
        self.client.force_login(self.test_student)

        # Students should not have access to the library pages
        self.assert403('library:quest_list')
        self.assert403('library:import_quest', args=[self.library_quest.import_id])

    def test_all_library_quest_page_status_codes__for_staff(self):
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

    def test_import_quest__to_current_deck(self):
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

    def test_import_quest__post_when_quest_exists_locally_is_denied(self):
        """POSTing to import a quest whose import_id already exists on the local deck is blocked (403), not duplicated."""
        self.client.force_login(self.test_teacher)

        local_quest = baker.make(Quest)
        with library_schema_context():
            library_quest = baker.make(Quest, import_id=local_quest.import_id)

        url = reverse('library:import_quest', args=[library_quest.import_id])
        response = self.client.post(url)

        self.assertEqual(response.status_code, 403)
        # the local quest was not duplicated by the blocked import
        self.assertEqual(Quest.objects.all_including_archived().filter(import_id=local_quest.import_id).count(), 1)

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
        The staff sidebar should show the Library link if enable_shared_library is enabled.
        Tests that it doesn't show when enable_shared_library=False
        Tests that it does show when enable_shared_library=True
        """
        # Make sure enable_shared_library is initially disabled
        staff = baker.make(User, is_staff=True)
        self.client.force_login(staff)

        self.config.enable_shared_library = False
        self.config.full_clean()
        self.config.save()

        # Login as staff
        self.client.force_login(self.test_teacher)

        # The Library pages themselves 404 while the feature is off, so check the
        # sidebar on a page staff can still reach.
        response = self.client.get(reverse('quests:quests'))
        # Checks if the html in the sidebar for library is there (shouldn't be)
        self.assertNotContains(response, 'id="lg-menu-library"')

        # Now enable the shared library
        self.config.enable_shared_library = True
        self.config.full_clean()
        self.config.save()

        # Re-fetch the response after config change
        response = self.client.get(reverse('library:quest_list'))

        # Checks if the html in the sidebar for library is there (should be)
        self.assertContains(response, 'id="lg-menu-library"')

    def test_require_export_permission__denied_non_owner_and_staff_permission_disabled(self):
        """
        Test that a non-owner cannot export a quest when staff export is disabled.
        """
        self.config.allow_staff_export = False
        self.config.full_clean()
        self.config.save()

        self.client.force_login(self.test_teacher)

        url = reverse("library:export_quest", kwargs={"quest_import_id": str(self.local_quest.import_id)})
        response = self.client.post(url, data=AGREED_LICENCE)

        self.assertEqual(response.status_code, 403)

    def test_require_export_permission__allowed_owner_and_staff_permission_disabled(self):
        """
        Test that the deck owner can export a quest even when staff export is disabled.
        """
        self.config.allow_staff_export = False
        self.config.full_clean()
        self.config.save()

        deck_owner = self.config.deck_owner

        self.client.force_login(deck_owner)

        url = reverse('library:export_quest', args=[self.local_quest.import_id])
        response = self.client.get(url)
        self.assert200URL(url)
        self.assertContains(response, self.local_quest.name)

    def test_require_export_permission__allowed_non_owner_and_staff_permission_enabled(self):
        """
        Test that a non-owner can export a quest when staff export is enabled.
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()

        self.client.force_login(self.test_teacher)

        url = reverse('library:export_quest', args=[self.local_quest.import_id])
        response = self.client.get(url)
        self.assert200URL(url)
        self.assertContains(response, self.local_quest.name)

    def test_export_get__shows_error_if_quest_already_in_library(self):
        """
        Test that the export confirmation view shows an error if the quest already exists in the library,
        whether the existing library quest is archived or not. Exporting again should not be allowed
        in either case.
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()

        self.client.force_login(self.test_teacher)

        url = reverse('library:export_quest', args=[self.shared_quest.import_id])
        response = self.client.get(url)
        self.assertContains(response, "A quest with the same import ID already exists in the shared library. Exporting again is not allowed.")

        # Archive the quest to test it again but against an archived quest
        with library_schema_context():
            self.shared_quest.archived = True
            self.shared_quest.full_clean()
            self.shared_quest.save()

        url = reverse('library:export_quest', args=[self.shared_quest.import_id])
        response = self.client.get(url)
        self.assertContains(response, "A quest with the same import ID already exists in the shared library. Exporting again is not allowed.")

    def test_export_post__success(self):
        """
        Test that exporting a quest to the library succeeds and notifies all library staff except the sender (deck_ai).
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()

        self.client.force_login(self.test_teacher)  # user performing export

        url = reverse('library:export_quest', args=[self.local_quest.import_id])
        response = self.client.post(url, data=AGREED_LICENCE)

        self.assertRedirects(response, reverse('quests:quests'))

        with library_schema_context():
            exported_quest = Quest.objects.get(import_id=self.local_quest.import_id)
            self.assertIsNotNone(exported_quest)

            deck_ai = User.objects.get(pk=SiteConfig.get().deck_ai.pk)

            # Get all active staff users in the library schema
            staff_users = User.objects.filter(is_active=True, is_staff=True)

            # For each staff user except deck_ai (sender), check notification exists
            for user in staff_users:
                if user == deck_ai:
                    continue

                exists = Notification.objects.filter(
                    recipient=user,
                    target_object_id=exported_quest.pk,
                    verb__icontains="exported a quest"
                ).exists()
                self.assertTrue(exists, f"Expected notification not found for staff user {user.username}.")

    @patch("library.views.send_email_message.apply_async")
    def test_export_post__emails_library_staff_and_messages_sharer(self, mock_apply_async):
        """Pushing a quest emails active Library staff (with the quest name, who shared
        it, and a review link) and tells the sharer it's pending review (#1949)."""
        # Give the library a staff member with an email; the default library staff
        # (deck_owner/deck_ai) have no address, so nothing would be sent otherwise.
        with library_schema_context():
            librarian = User.objects.create_user('librarian', email='librarian@example.com', is_staff=True)

        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()

        self.client.force_login(self.test_teacher)

        url = reverse('library:export_quest', args=[self.local_quest.import_id])
        response = self.client.post(url, data=AGREED_LICENCE)
        self.assertRedirects(response, reverse('quests:quests'))

        # An email was dispatched asynchronously to the library staff member.
        mock_apply_async.assert_called_once()
        subject, message, recipient_list = mock_apply_async.call_args.kwargs['args']
        self.assertIn(librarian.email, recipient_list)
        self.assertIn(self.local_quest.name, subject)
        self.assertIn(self.local_quest.name, message)
        self.assertIn(str(self.test_teacher), message)  # who shared it
        self.assertIn('Review and publish it here', message)  # where to review/publish
        # The review/publish link is a real clickable href pointing at the Library deck.
        self.assertIn('<a href="https://library.test.com', message)
        # The email names the source deck the content came from and links back to it (#1949).
        self.assertIn('<a href="https://tenant.test.com">https://tenant.test.com</a>', message)

        # The sharer is told the content is pending review before it appears.
        sharer_messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(
            any('review and publish it' in m for m in sharer_messages),
            f"Expected a pending-review message, got: {sharer_messages}",
        )

    def test_export_post__denied_if_quest_already_exists_in_library(self):
        """
        Test that a POST request to export is denied with 403 if the quest already exists in the library.
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()

        self.client.force_login(self.test_teacher)

        url = reverse("library:export_quest", kwargs={"quest_import_id": str(self.shared_quest.import_id)})
        response = self.client.post(url, data=AGREED_LICENCE)

        self.assertEqual(response.status_code, 403)


class CampaignLibraryTestCases(LibraryTenantTestCaseMixin):
    @classmethod
    def setUpTestData(cls):
        """Create library and local categories/quests plus teacher/student users."""
        cls.local_category = baker.make(Category)
        cls.shared_category = baker.make(Category)

        baker.make(Quest, campaign=cls.local_category, published=True)
        baker.make(Quest, campaign=cls.local_category, published=True)

        with library_schema_context():
            # Create a category in the library tenant
            cls.library_category = baker.make(Category)
            cls.library_quest = baker.make(Quest, campaign=cls.library_category, published=True)
            baker.make(Category, import_id=cls.shared_category.import_id)

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student = User.objects.create_user('test_student', is_staff=False)

    def setUp(self):
        """Set up the active semester, site config, and deck owner."""
        super().setUp()
        self.sem = SiteConfig.get().active_semester

        self.config = SiteConfig.get()
        self.deck_owner = self.config.deck_owner

    def test_all_library_category_page_status_codes__for_anonymous(self):
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

    def test_all_library_category_page_status_codes__for_students(self):
        """
        Tests that the library pages return the correct status codes for student users.
        """
        self.client.force_login(self.test_student)

        # Students should not have access to the library pages
        self.assert403('library:category_list')
        self.assert403('library:import_category', args=[self.library_category.import_id])
        self.assert403('library:category_detail_view', args=[self.library_category.import_id])

    def test_all_library_category_page_status_codes__for_staff(self):
        """
        Tests that the library pages return the correct status codes for staff users.
        """
        self.client.force_login(self.test_teacher)

        # Staff should have access to the library pages
        self.assert200('library:category_list')
        self.assert200('library:import_category', args=[self.library_category.import_id])
        self.assert200('library:category_detail_view', args=[self.library_category.import_id])

    def test_import_campaign___already_exists(self):
        """Importing a campaign already present on the deck shows a matching-name warning."""
        self.client.force_login(self.test_teacher)
        with library_schema_context():
            # Create a category in the library tenant
            library_category = baker.make(Category, title='Existing Campaign')

        # Create a category in the current tenant with the same import_id
        baker.make(Category, import_id=library_category.import_id, title=library_category.name)

        import_url = reverse('library:import_category', args=[library_category.import_id])

        response = self.client.get(import_url)
        self.assertContains(response, 'Your deck already contains a campaign with a matching name.')

    def test_import_campaign__post_when_campaign_exists_locally_is_denied(self):
        """POSTing to import a campaign whose import_id already exists on the local deck is blocked (403), not duplicated."""
        self.client.force_login(self.test_teacher)

        with library_schema_context():
            library_category = baker.make(Category)
        # a local campaign already shares the import_id
        baker.make(Category, import_id=library_category.import_id)

        import_url = reverse('library:import_category', args=[library_category.import_id])
        response = self.client.post(import_url)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(Category.objects.filter(import_id=library_category.import_id).count(), 1)

    def test_category_detail__with_no_displayed_quests_has_empty_quest_info(self):
        """The campaign detail view returns an empty quest_info list for a library campaign with no displayable quests."""
        self.client.force_login(self.test_teacher)

        with library_schema_context():
            empty_category = baker.make(Category)  # a campaign with no quests

        url = reverse('library:category_detail_view', args=[empty_category.import_id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['quest_info'], [])
        self.assertEqual(list(response.context['category_displayed_quests']), [])

    def test_import_campaign___success(self):
        """Importing a library campaign copies it and its quests as unpublished onto the deck."""
        self.client.force_login(self.test_teacher)
        # Capture baseline to assert relative change after import
        initial_category_count = Category.objects.count()

        with library_schema_context():
            library_campaign = baker.make(Category)
            baker.make(Quest, published=True, campaign=library_campaign, _quantity=3)
            self.assertEqual(library_campaign.quest_set.count(), 3)

        import_url = reverse('library:import_category', args=[library_campaign.import_id])

        response = self.client.post(import_url)
        self.assertEqual(response.url, reverse('quests:categories_inactive'))
        # Expect one additional category after import
        self.assertEqual(Category.objects.count(), initial_category_count + 1)
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

    def test_import_campaign_get__identifies_existing_local_quests(self):
        """
        Ensure the import campaign view correctly identifies which quests from the
        selected library campaign already exist locally and includes their import IDs
        in the response context. Also verifies that the warning message is shown when
        such conflicts are detected.
        """
        self.client.force_login(self.test_teacher)

        with library_schema_context():
            # Create a campaign in the library schema with quests
            library_campaign = baker.make(Category)
            # Create 3 published quests in this library campaign
            library_quests = baker.make(Quest, campaign=library_campaign, published=True, _quantity=3)

        # Import one of these quests individually into the local schema to simulate existing local quest
        import_quest_to(destination_schema=connection.schema_name, quest_import_id=library_quests[0].import_id)

        # Now call the import campaign GET view
        import_url = reverse('library:import_category', args=[library_campaign.import_id])
        response = self.client.get(import_url)

        self.assertEqual(response.status_code, 200)

        # The context variable 'local_quest_import_ids' should include the import_id of the imported quest
        local_ids = response.context['local_quest_import_ids']
        self.assertIn(library_quests[0].import_id, local_ids)

        # The other quests' import_ids should not be in local_quest_import_ids
        for quest in library_quests[1:]:
            self.assertNotIn(quest.import_id, local_ids)

        # Check the warning text appears in the rendered content
        self.assertContains(response, "One or more quests in this campaign already exist")

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

    def test_campaigns_tab__shows_the_library_actions_not_the_local_ones(self):
        """The Library's campaign list offers the import action, not the deck's own campaign
        actions (edit, export, delete), and carries the Library's introductory blurb.

        This page and the deck's own campaign list share
        `quest_manager/tab_campaigns_list.html`, which tells them apart by the
        `is_library_view` context flag, so this guards the flag being set here (issue #2380).
        """
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:category_list'))

        self.assertTrue(response.context['is_library_view'])
        self.assertContains(response, reverse('library:import_category', args=[self.library_category.import_id]))
        self.assertContains(response, 'Import this Campaign into your Deck')
        self.assertContains(response, 'EXPERIMENTAL!')
        # the local campaign actions act on the deck's own campaigns, which aren't what's listed here
        self.assertNotContains(response, 'Edit this campaign')
        self.assertNotContains(response, 'Export this Campaign to the Library')

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
        # Capture baseline to assert relative change after campaign import
        initial_category_count = Category.objects.count()

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

        # Expect one additional category after import
        self.assertEqual(Category.objects.count(), initial_category_count + 1)

        # Reload quests from DB
        unpublished_local_quest = Quest.objects.get(import_id=library_quests[0].import_id)
        published_local_quest.refresh_from_db()

        self.assertFalse(unpublished_local_quest.published)
        self.assertTrue(published_local_quest.published)

    def test_import_campaign_to__unknown_campaign_id_skips_deactivation(self):
        """When no local Category matches the given campaign_import_id, the importer finishes
        without trying to deactivate a campaign (the `if category` false branch)."""
        with library_schema_context():
            library_quests = baker.make(Quest, published=True, _quantity=1)

        result = import_campaign_to(
            destination_schema=connection.schema_name,
            quest_import_ids=[q.import_id for q in library_quests],
            campaign_import_id=uuid.uuid4(),  # no local Category will match this
        )

        self.assertIsNotNone(result)

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

            # Make a current quest on the library and put it in a campaign: should be included
            baker.make(Quest, campaign=included, published=True, archived=False)

            # Make an archived quest on the library and put it in a campaign: should not count
            baker.make(Quest, campaign=excluded_archived, published=True, archived=True)

            # Make and invisible quest (draft) on the library and put it in a campaign: should not count
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

    def test_export__permission_denied_for_non_owner_staff_export_disabled(self):
        """
        Ensure that staff users who are not the deck owner are denied access
        to the export view when staff export permission is disabled.
        """
        self.config.allow_staff_export = False
        self.config.full_clean()
        self.config.save()
        self.client.force_login(self.test_teacher)

        url = reverse('library:export_category', kwargs={'campaign_import_id': str(self.library_category.import_id)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

        response = self.client.post(url, data=AGREED_LICENCE)
        self.assertEqual(response.status_code, 403)

    def test_export__permission_allowed_for_owner_staff_export_disabled(self):
        """
        Ensure that the deck owner can access the export view even when
        staff export permission is disabled.
        """
        self.config.allow_staff_export = False
        self.config.full_clean()
        self.config.save()
        self.client.force_login(self.deck_owner)

        url = reverse('library:export_category', kwargs={'campaign_import_id': str(self.local_category.import_id)})
        # Ensure at least one additional staff user exists in the library schema
        with library_schema_context():
            baker.make(User, is_staff=True, is_active=True)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.local_category.name)

    def test_export__permission_allowed_for_non_owner_staff_export_enabled(self):
        """
        Ensure that staff users other than the deck owner can access the export view
        when staff export permission is enabled.
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()
        self.client.force_login(self.test_teacher)

        url = reverse('library:export_category', kwargs={'campaign_import_id': str(self.local_category.import_id)})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.local_category.name)

    def test_export_get__shows_error_if_campaign_already_exists_in_library(self):
        """
        Ensure the export GET view displays an error message if the campaign
        already exists in the shared library schema, preventing duplicate exports.
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()
        self.client.force_login(self.test_teacher)

        url = reverse('library:export_category', kwargs={'campaign_import_id': str(self.shared_category.import_id)})
        response = self.client.get(url)
        self.assertContains(response, "A campaign with the same import ID already exists in the shared library")

    def test_export_post__denied_if_campaign_exists(self):
        """
        Ensure that attempting to POST (perform export) for a campaign that already
        exists in the library schema is forbidden and returns HTTP 403.
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()
        self.client.force_login(self.test_teacher)

        url = reverse('library:export_category', kwargs={'campaign_import_id': str(self.shared_category.import_id)})
        response = self.client.post(url, data=AGREED_LICENCE)
        self.assertEqual(response.status_code, 403)

    def test_export_get__disables_button_if_no_quests(self):
        """
        The confirmation page should disable the export button if the campaign has no quests.
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()
        self.client.force_login(self.test_teacher)

        empty_campaign = Category.objects.create(title="Empty Campaign")

        url = reverse('library:export_category', args=[empty_campaign.import_id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Look for UI safeguard: button should be disabled
        self.assertContains(response, 'You cannot export a campaign with no published quests.')

    def test_export_post__successful_export_and_notifications(self):
        """
        Test that a successful campaign export via POST:
        - Redirects the user to the quests categories page
        - Creates the campaign in the library schema
        - Sends notifications to all active staff users (except the deck_ai user)
        about the export action
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()
        self.client.force_login(self.test_teacher)

        url = reverse('library:export_category', kwargs={'campaign_import_id': str(self.local_category.import_id)})
        response = self.client.post(url, data=AGREED_LICENCE)
        self.assertRedirects(response, reverse('quests:categories'))

        with library_schema_context():
            exported_campaign = Category.objects.filter(import_id=self.local_category.import_id).first()
            self.assertIsNotNone(exported_campaign)
            self.assertFalse(exported_campaign.published)

            deck_ai = User.objects.get(pk=SiteConfig.get().deck_ai.pk)
            staff_users = User.objects.filter(is_active=True, is_staff=True)

            for user in staff_users:
                if user == deck_ai:
                    continue
                self.assertTrue(
                    Notification.objects.filter(
                        recipient=user,
                        verb__icontains="exported a campaign",
                        target_object_id=exported_campaign.pk,
                    ).exists(),
                    f"Notification not found for {user.username}"
                )

    @patch("library.views.send_email_message.apply_async")
    def test_export_post__emails_library_staff_and_messages_sharer(self, mock_apply_async):
        """Pushing a campaign emails active Library staff (with the campaign name, who
        shared it, and a review link) and tells the sharer it's pending review (#1949)."""
        # Give the library a staff member with an email; the default library staff
        # (deck_owner/deck_ai) have no address, so nothing would be sent otherwise.
        with library_schema_context():
            librarian = User.objects.create_user('librarian', email='librarian@example.com', is_staff=True)

        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()

        self.client.force_login(self.test_teacher)

        url = reverse('library:export_category', kwargs={'campaign_import_id': str(self.local_category.import_id)})
        response = self.client.post(url, data=AGREED_LICENCE)
        self.assertRedirects(response, reverse('quests:categories'))

        # An email was dispatched asynchronously to the library staff member.
        mock_apply_async.assert_called_once()
        subject, message, recipient_list = mock_apply_async.call_args.kwargs['args']
        self.assertIn(librarian.email, recipient_list)
        self.assertIn(self.local_category.name, subject)
        self.assertIn(self.local_category.name, message)
        self.assertIn(str(self.test_teacher), message)  # who shared it
        self.assertIn('Review and publish it here', message)  # where to review/publish
        # The review/publish link is a real clickable href pointing at the Library deck.
        self.assertIn('<a href="https://library.test.com', message)
        # The email names the source deck the content came from and links back to it (#1949).
        self.assertIn('<a href="https://tenant.test.com">https://tenant.test.com</a>', message)

        # The sharer is told the content is pending review before it appears.
        sharer_messages = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(
            any('review and publish it' in m for m in sharer_messages),
            f"Expected a pending-review message, got: {sharer_messages}",
        )

    def test_export__campaign_with_conflicting_quests_clones_correctly(self):
        """
        Ensure that exporting a campaign where some quests already exist in the library:
        - Clones conflicting quests
        - Assigns new import_ids
        - Appends a unique suffix to the quest name
        - Sets published=False on the clones
        - Works correctly when exporting more than once:
            * First run: mix of conflicting + non-conflicting quests
            * Second run: all quests are conflicts, all get cloned
        """
        self.client.force_login(self.test_teacher)

        # Step 1: create a local campaign with quests
        local_campaign = baker.make(Category, title="Local Campaign")
        local_quests = [
            baker.make(Quest, campaign=local_campaign, published=True, name="Quest 1"),
            baker.make(Quest, campaign=local_campaign, published=True, name="Quest 2"),
        ]

        # Step 2: simulate a conflict in the library (one of the quests already exists)
        with library_schema_context():
            conflicting_quest = deepcopy(local_quests[0])
            conflicting_quest.pk = None
            conflicting_quest.import_id = local_quests[0].import_id
            conflicting_quest.campaign = None
            conflicting_quest.full_clean()
            conflicting_quest.save()

        def run_export_and_assert(expect_non_conflicting: bool):
            """Helper to run export and validate clone naming/suffixing."""
            export_campaign_and_copy_quests(
                source_schema=self.tenant.schema_name,
                campaign_import_id=local_campaign.import_id,
            )
            with library_schema_context():
                exported_campaign = Category.objects.get(import_id=local_campaign.import_id)
                self.assertEqual(exported_campaign.quest_set.count(), 2)

                # One or more cloned quests should exist
                cloned_quests = exported_campaign.quest_set.exclude(
                    import_id__in=[q.import_id for q in local_quests]
                )
                self.assertTrue(cloned_quests.exists())
                for cq in cloned_quests:
                    self.assertFalse(cq.published)
                    self.assertIn("(Exported on", cq.name)

                if expect_non_conflicting:
                    # Verify the non-conflicting quest was exported normally
                    non_conflicting_quest = exported_campaign.quest_set.get(
                        import_id=local_quests[1].import_id
                    )
                    self.assertEqual(non_conflicting_quest.name, local_quests[1].name)
                    self.assertFalse(non_conflicting_quest.published)
                else:
                    # When all quests are conflicts, both should be clones
                    self.assertEqual(cloned_quests.count(), len(local_quests))
                    self.assertEqual(
                        exported_campaign.quest_set.filter(
                            import_id__in=[q.import_id for q in local_quests]
                        ).count(),
                        0,
                        "Expected no original import_ids when all quests conflict",
                    )

        # Step 3: First export (mix of conflict + non-conflict)
        run_export_and_assert(expect_non_conflicting=True)

        # Step 4: Delete campaign in library → re-run export (now all quests conflict)
        with library_schema_context():
            Category.objects.filter(import_id=local_campaign.import_id).delete()
        run_export_and_assert(expect_non_conflicting=False)


class LibraryOverviewTestsCase(LibraryTenantTestCaseMixin):
    @classmethod
    def setUpTestData(cls):
        """Create a published library campaign/quest plus teacher/student users."""
        with library_schema_context():
            # Set up a campaign to test with later
            cls.library_campaign = baker.make(Category, published=True)
            # Set up a quest to test with later
            cls.library_quest = baker.make(Quest, campaign=cls.library_campaign)

        # Need a teacher before students can be created or the profile creation will fail when trying to notify
        cls.test_teacher = User.objects.create_user('test_teacher', is_staff=True)
        cls.test_student = User.objects.create_user('test_student', is_staff=False)

    def test_library_overview__redirects_anonymous(self):
        """
        Anonymous users should be redirected to the login page when accessing the library overview.
        """
        self.assertRedirectsLogin('library:quest_list')

    def test_library_overview__for_students(self):
        """
        Authenticated students should receive a 403 Forbidden when trying to access the library
        """
        self.client.force_login(self.test_student)
        self.assert403('library:quest_list')

    def test_library_overview__for_staff_default_tab(self):
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

    def test_library_overview__quests_tab_is_paginated(self):
        """The quests tab sends one page of quests, not the whole Library (#2379).

        With more quests than fit on a page, the first page carries exactly `paginate_by` of
        them and the pagination controls appear; the second page carries the rest.
        """
        page_size = LibraryQuestListView.paginate_by
        with library_schema_context():
            # Quest.name is unique, so these can't be made in one _quantity call
            for i in range(page_size):
                baker.make(Quest, name=f'Paged library quest {i}', campaign=self.library_campaign, published=True)
            total = Quest.objects.get_active().count()

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('library:quest_list'))

        self.assertGreater(total, page_size)
        self.assertEqual(len(response.context['library_quests']), page_size)
        self.assertEqual(response.context['page_obj'].paginator.count, total)
        self.assertEqual(response.context['num_quests'], total)
        self.assertContains(response, 'page=2')

        response = self.client.get(reverse('library:quest_list'), {'page': 2})
        self.assertEqual(len(response.context['library_quests']), min(page_size, total - page_size))

    def test_library_overview__quests_tab_page_out_of_range_shows_the_last_page(self):
        """A ?page= that is junk or past the end lands on a real page instead of erroring.

        Someone editing the URL, or following a stale link after quests were removed, should
        get the nearest page rather than a 404.
        """
        self.client.force_login(self.test_teacher)

        for bad_page in ('9999', 'not-a-number'):
            with self.subTest(page=bad_page):
                response = self.client.get(reverse('library:quest_list'), {'page': bad_page})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['page_obj'].number, 1)

    def test_library_overview__quests_tab_page_below_one_shows_the_first_page(self):
        """`?page=0` and `?page=-1` land on the first page, not the last.

        Django's `get_page()` treats any out-of-range number as "the last page", which is
        right for a stale link to a page that no longer exists and wrong for a number that
        was never a page: nobody typing 0 or -1 is asking for the end of the list.
        """
        page_size = LibraryQuestListView.paginate_by
        with library_schema_context():
            # Quest.name is unique, so these can't be made in one _quantity call
            for i in range(page_size):
                baker.make(Quest, name=f'Clamped page quest {i}', published=True)

        self.client.force_login(self.test_teacher)

        for bad_page in ('0', '-1'):
            with self.subTest(page=bad_page):
                response = self.client.get(reverse('library:quest_list'), {'page': bad_page})

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['page_obj'].number, 1)
                self.assertGreater(response.context['page_obj'].paginator.num_pages, 1)

    def test_library_overview__quests_tab_search_matches_name_campaign_and_tag(self):
        """Searching covers the whole Library, and matches a quest's name, campaign or tag.

        The search runs in the database rather than over the rows already sent to the browser
        (#2379), so a match on a later page is still found.
        """
        with library_schema_context():
            campaign = baker.make(Category, title='Recursion Fundamentals', published=True)
            by_name = baker.make(Quest, name='All about recursion', published=True)
            by_campaign = baker.make(Quest, name='Towers of Hanoi', campaign=campaign, published=True)
            by_tag = baker.make(Quest, name='Fractal trees', published=True)
            by_tag.tags.add('recursion')
            total = Quest.objects.get_active().count()

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('library:quest_list'), {'q': 'recursion'})

        listed = response.context['library_quests']
        self.assertCountEqual(listed, [by_name, by_campaign, by_tag])
        # the quest seeded by setUpTestData matches none of the three, so it is filtered out
        self.assertNotIn(self.library_quest, listed)
        self.assertEqual(response.context['search_term'], 'recursion')
        self.assertEqual(response.context['num_matching_quests'], 3)
        # the tab badge keeps counting the whole Library, not the search results
        self.assertEqual(response.context['num_quests'], total)

    def test_library_overview__quests_tab_search_narrows_on_every_word(self):
        """Several search words all have to match, though not all against the same field.

        This is what the in-browser search did before the search moved to the server, and it
        is what makes a two-word search useful: "recursion python" is a narrowing, not a
        request for everything about either.
        """
        with library_schema_context():
            both = baker.make(Quest, name='Recursion: base cases', published=True)
            both.tags.add('python')
            only_recursion = baker.make(Quest, name='Recursion in art', published=True)
            only_recursion.tags.add('graphics')

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('library:quest_list'), {'q': 'recursion python'})

        listed = response.context['library_quests']
        self.assertIn(both, listed)
        self.assertNotIn(only_recursion, listed)

    def test_library_overview__quests_tab_search_lists_each_quest_once(self):
        """A quest whose name and tags both match the search is still listed once.

        Joining on tags multiplies the row per matching tag, so without a distinct() the same
        quest would appear several times.
        """
        with library_schema_context():
            quest = baker.make(Quest, name='Recursion practice', published=True)
            quest.tags.add('recursion', 'recursion-drills')

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('library:quest_list'), {'q': 'recursion'})

        self.assertEqual(list(response.context['library_quests']), [quest])
        self.assertEqual(response.context['num_matching_quests'], 1)

    def test_library_overview__quests_tab_search_with_no_matches(self):
        """A search that matches nothing says so, and offers a way back to the full Library."""
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:quest_list'), {'q': 'nothing matches this'})

        self.assertEqual(list(response.context['library_quests']), [])
        self.assertContains(response, 'No quests in the Library match')
        self.assertContains(response, 'Clear this search')

    def test_library_overview__quests_tab_pagination_links_keep_the_search(self):
        """Paging through search results keeps the search: page links carry the `q` term.

        Without it, clicking page 2 would silently drop back to the unfiltered Library.
        """
        page_size = LibraryQuestListView.paginate_by
        with library_schema_context():
            # Quest.name is unique, so these can't be made in one _quantity call
            for i in range(page_size + 1):
                baker.make(Quest, name=f'Recursion drill {i}', published=True)

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('library:quest_list'), {'q': 'recursion'})

        self.assertContains(response, 'q=recursion')
        self.assertContains(response, 'page=2')

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


class ExporterErrorPathTests(LibraryTenantTestCaseMixin):
    """Error-handling branches of ``library.exporter``: the cases where a quest or
    campaign export can't complete and the exporter re-raises a clearer exception."""

    def test_export_quest_to_library__unknown_import_id_raises_does_not_exist(self):
        """Exporting a quest whose import_id isn't in the source schema raises Quest.DoesNotExist."""
        with self.assertRaises(Quest.DoesNotExist):
            export_quest_to_library(source_schema=self.tenant.schema_name, quest_import_id=uuid.uuid4())

    @patch("library.exporter.LibraryQuestResource.import_data")
    def test_clone_quests_into_library__import_failure_wrapped_as_validation_error(self, mock_import_data):
        """A database error while copying conflicting quests is re-raised with context."""
        mock_import_data.side_effect = IntegrityError("duplicate key")
        quest = baker.make(Quest, published=True)
        with self.assertRaisesMessage(ValidationError, "Failed to copy conflicting quests to library schema"):
            clone_quests_into_library(source_schema=self.tenant.schema_name, quests=[quest])

    @patch("library.exporter.LibraryQuestResource.import_data")
    def test_export_quest_to_library__import_failure_wrapped_as_validation_error(self, mock_import_data):
        """A database error while importing a quest is re-raised as a clearer ValidationError with context."""
        mock_import_data.side_effect = IntegrityError("duplicate key")
        quest = baker.make(Quest, published=True)
        with self.assertRaisesMessage(ValidationError, "Failed to import quest to library schema"):
            export_quest_to_library(source_schema=self.tenant.schema_name, quest_import_id=quest.import_id)

    def test_export_campaign_to_library__no_published_quests_raises_validation_error(self):
        """Exporting a campaign that has no published quests (and no skip list) is rejected with a ValidationError."""
        campaign = baker.make(Category)
        baker.make(Quest, campaign=campaign, published=False)
        with self.assertRaisesMessage(ValidationError, "Cannot export a campaign without any published quests."):
            export_campaign_to_library(source_schema=self.tenant.schema_name, campaign_import_id=campaign.import_id)

    @patch("library.exporter.LibraryQuestResource.import_data")
    def test_export_campaign_to_library__import_failure_wrapped_as_validation_error(self, mock_import_data):
        """A validation error while importing a campaign is re-raised as a clearer ValidationError with context."""
        mock_import_data.side_effect = ValidationError("bad data")
        campaign = baker.make(Category)
        baker.make(Quest, campaign=campaign, published=True)
        with self.assertRaisesMessage(ValidationError, "Failed to import campaign to library schema"):
            export_campaign_to_library(source_schema=self.tenant.schema_name, campaign_import_id=campaign.import_id)


class SharedLibraryDisabledTests(LibraryTenantTestCaseMixin):
    """Every Library view is unreachable on a deck that has the feature turned off.

    `SiteConfig.enable_shared_library` used to hide the sidebar link and nothing
    else, leaving every Library URL live (and importable) on a deck that had
    opted out.
    """

    @classmethod
    def setUpTestData(cls):
        """Create published Library content and a staff user on the local deck."""
        with library_schema_context():
            cls.library_campaign = baker.make(Category, published=True)
            cls.library_quest = baker.make(Quest, campaign=cls.library_campaign, published=True, archived=False)

        cls.local_quest = baker.make(Quest, published=True)
        cls.local_campaign = baker.make(Category)
        baker.make(Quest, campaign=cls.local_campaign, published=True)
        cls.test_teacher = User.objects.create_user('disabled_teacher', is_staff=True)

    def setUp(self):
        """Turn the Shared Library back off, overriding the base class default."""
        super().setUp()
        self.config = SiteConfig.get()
        self.config.enable_shared_library = False
        self.config.allow_staff_export = True
        self.config.save()
        self.client.force_login(self.test_teacher)

    def test_library_views__return_404_when_shared_library_disabled(self):
        """Staff hitting any Library URL on an opted-out deck get a 404."""
        urls = [
            reverse('library:quest_list'),
            reverse('library:category_list'),
            reverse('library:import_quest', args=[self.library_quest.import_id]),
            reverse('library:import_category', args=[self.library_campaign.import_id]),
            reverse('library:category_detail_view', args=[self.library_campaign.import_id]),
            reverse('library:export_quest', args=[self.local_quest.import_id]),
            reverse('library:export_category', args=[self.local_campaign.import_id]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assert404URL(url)

    def test_import_quest_post__does_nothing_when_shared_library_disabled(self):
        """A POST to the quest import URL cannot pull content onto an opted-out deck."""
        response = self.client.post(reverse('library:import_quest', args=[self.library_quest.import_id]))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Quest.objects.all_including_archived().filter(import_id=self.library_quest.import_id).exists())

    def test_import_campaign_post__does_nothing_when_shared_library_disabled(self):
        """A POST to the campaign import URL cannot pull content onto an opted-out deck."""
        response = self.client.post(reverse('library:import_category', args=[self.library_campaign.import_id]))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Category.objects.filter(import_id=self.library_campaign.import_id).exists())

    def test_export_quest_post__does_nothing_when_shared_library_disabled(self):
        """A POST to the quest export URL cannot push content from an opted-out deck."""
        response = self.client.post(
            reverse('library:export_quest', args=[self.local_quest.import_id]), data=AGREED_LICENCE
        )

        self.assertEqual(response.status_code, 404)
        with library_schema_context():
            self.assertFalse(Quest.objects.all_including_archived().filter(import_id=self.local_quest.import_id).exists())


class UnreviewedLibraryContentTests(LibraryTenantTestCaseMixin):
    """Content awaiting a Library admin's review must not be importable.

    Pushed content lands unpublished and is invisible until reviewed (#1949).
    That gate only filtered the listing pages, so a POST straight to an import
    URL pulled unreviewed content down.
    """

    @classmethod
    def setUpTestData(cls):
        """Create unpublished (pending review) Library content and a local staff user."""
        with library_schema_context():
            cls.pending_quest = baker.make(Quest, published=False, archived=False)
            cls.pending_campaign = baker.make(Category, published=False)
            cls.pending_campaign_quest = baker.make(
                Quest, campaign=cls.pending_campaign, published=True, archived=False
            )
        cls.test_teacher = User.objects.create_user('pending_teacher', is_staff=True)

    def setUp(self):
        """Log in as staff on a deck with the Shared Library enabled."""
        super().setUp()
        self.client.force_login(self.test_teacher)

    def test_import_quest_get__redirects_when_quest_awaits_review(self):
        """The confirmation page for an unpublished Library quest sends the user back with a warning."""
        response = self.client.get(reverse('library:import_quest', args=[self.pending_quest.import_id]))

        self.assertRedirects(response, reverse('library:quest_list'))
        self.assertWarningMessage(response)

    def test_import_quest_post__refuses_a_quest_awaiting_review(self):
        """Posting the import URL for an unpublished Library quest imports nothing."""
        response = self.client.post(reverse('library:import_quest', args=[self.pending_quest.import_id]))

        self.assertRedirects(response, reverse('library:quest_list'))
        self.assertFalse(Quest.objects.all_including_archived().filter(import_id=self.pending_quest.import_id).exists())

    def test_import_campaign_get__redirects_when_campaign_awaits_review(self):
        """The confirmation page for an unpublished Library campaign sends the user back with a warning."""
        response = self.client.get(reverse('library:import_category', args=[self.pending_campaign.import_id]))

        self.assertRedirects(response, reverse('library:category_list'))
        self.assertWarningMessage(response)

    def test_import_campaign_post__refuses_a_campaign_awaiting_review(self):
        """Posting the import URL for an unpublished Library campaign imports nothing, quests included."""
        response = self.client.post(reverse('library:import_category', args=[self.pending_campaign.import_id]))

        self.assertRedirects(response, reverse('library:category_list'))
        self.assertFalse(Category.objects.filter(import_id=self.pending_campaign.import_id).exists())
        self.assertFalse(
            Quest.objects.all_including_archived().filter(import_id=self.pending_campaign_quest.import_id).exists()
        )

    def test_category_detail_view__redirects_when_campaign_awaits_review(self):
        """The Library campaign detail page is not a peephole into unreviewed content."""
        response = self.client.get(reverse('library:category_detail_view', args=[self.pending_campaign.import_id]))

        self.assertRedirects(response, reverse('library:category_list'))
        self.assertWarningMessage(response)

    def test_import_quest_to__refuses_a_quest_awaiting_review(self):
        """The importer itself filters on published, not just the view above it."""
        with self.assertRaises(Quest.DoesNotExist):
            import_quest_to(destination_schema=connection.schema_name, quest_import_id=self.pending_quest.import_id)

    def test_import_quest__unknown_import_id_still_404s(self):
        """An import ID that is in no schema at all is a 404, not a redirect."""
        self.assert404URL(reverse('library:import_quest', args=[str(uuid.uuid4())]))


class ShareLicenceAgreementTests(LibraryTenantTestCaseMixin):
    """The CC BY-SA agreement holds the push server-side, not just in the browser."""

    @classmethod
    def setUpTestData(cls):
        """Create a local quest and campaign to share, and a staff user to share them."""
        cls.local_quest = baker.make(Quest, published=True, archived=False)
        cls.local_campaign = baker.make(Category)
        baker.make(Quest, campaign=cls.local_campaign, published=True, archived=False)
        cls.test_teacher = User.objects.create_user('licence_teacher', is_staff=True)

    def setUp(self):
        """Allow staff to export, and log in as one."""
        super().setUp()
        config = SiteConfig.get()
        config.allow_staff_export = True
        config.save()
        self.client.force_login(self.test_teacher)

    def test_export_quest_post__refused_without_the_licence_agreement(self):
        """A quest push with no licence checkbox is re-rendered with an error and shares nothing."""
        response = self.client.post(reverse('library:export_quest', args=[self.local_quest.import_id]), data={})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'agree to the Creative Commons license')
        with library_schema_context():
            self.assertFalse(Quest.objects.all_including_archived().filter(import_id=self.local_quest.import_id).exists())

    def test_export_campaign_post__refused_without_the_licence_agreement(self):
        """A campaign push with no licence checkbox is re-rendered with an error and shares nothing."""
        response = self.client.post(reverse('library:export_category', args=[self.local_campaign.import_id]), data={})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'agree to the Creative Commons license')
        with library_schema_context():
            self.assertFalse(Category.objects.filter(import_id=self.local_campaign.import_id).exists())

    def test_export_quest_post__succeeds_with_the_licence_agreement(self):
        """Ticking the box lets the push through, so the guard is not blocking everything."""
        response = self.client.post(
            reverse('library:export_quest', args=[self.local_quest.import_id]), data=AGREED_LICENCE
        )

        self.assertRedirects(response, reverse('quests:quests'))
        with library_schema_context():
            self.assertTrue(Quest.objects.all_including_archived().filter(import_id=self.local_quest.import_id).exists())

    def test_export_get__renders_the_licence_checkbox(self):
        """Both confirmation pages render the field name the form validates."""
        for url in (
            reverse('library:export_quest', args=[self.local_quest.import_id]),
            reverse('library:export_category', args=[self.local_campaign.import_id]),
        ):
            with self.subTest(url=url):
                self.assertContains(self.client.get(url), 'name="agree_license"')


class ContentOriginTests(LibraryTenantTestCaseMixin):
    """Where shared content came from is recorded on the push, and shown as attribution.

    Content travels under CC BY-SA 4.0, which asks for attribution, and nothing was
    recording who had shared what (#2377).
    """

    # what the deck the content is shared from is called, so the attribution has
    # something distinctive to render
    DECK_NAME = 'sharing-deck'

    @classmethod
    def setUpTestData(cls):
        """Create a local quest and campaign to share, and the staff user who shares them."""
        cls.local_quest = baker.make(Quest, name='A quest with an author', published=True, archived=False)
        cls.local_campaign = baker.make(Category, title='A campaign with an author')
        cls.campaign_quest = baker.make(Quest, campaign=cls.local_campaign, published=True, archived=False)
        cls.test_teacher = User.objects.create_user('sharing_teacher', is_staff=True)

    def setUp(self):
        """Allow staff to export, log in as one, and give the deck a recognizable name.

        The test tenant is created without a name, and an empty name would make the
        rendered attribution ("...of {deck}") impossible to assert on.
        """
        super().setUp()
        config = SiteConfig.get()
        config.allow_staff_export = True
        config.save()
        # the middleware re-fetches the tenant per request, so this has to reach the row
        Tenant.objects.filter(schema_name=connection.schema_name).update(name=self.DECK_NAME)
        self.tenant.name = self.DECK_NAME
        self.client.force_login(self.test_teacher)

    def test_export_quest_post__records_who_shared_it_and_from_where(self):
        """Pushing a quest stores the deck and the user, which is what attribution needs."""
        self.client.post(reverse('library:export_quest', args=[self.local_quest.import_id]), data=AGREED_LICENCE)

        with library_schema_context():
            origin = ContentOrigin.objects.get(
                import_id=self.local_quest.import_id, content_type=ContentOrigin.QUEST
            )

        self.assertEqual(origin.shared_by, 'sharing_teacher')
        self.assertEqual(origin.deck_name, self.DECK_NAME)
        self.assertEqual(origin.deck_url, self.tenant.get_root_url())

    def test_export_campaign_post__records_the_campaign_and_each_of_its_quests(self):
        """A campaign push attributes the campaign and every quest that travelled with it.

        A quest from a shared campaign can be imported on its own, so it needs its own
        attribution rather than only the campaign's.
        """
        self.client.post(reverse('library:export_category', args=[self.local_campaign.import_id]), data=AGREED_LICENCE)

        with library_schema_context():
            campaign_origin = ContentOrigin.objects.get(
                import_id=self.local_campaign.import_id, content_type=ContentOrigin.CAMPAIGN
            )
            quest_origin = ContentOrigin.objects.get(
                import_id=self.campaign_quest.import_id, content_type=ContentOrigin.QUEST
            )

        self.assertEqual(campaign_origin.shared_by, 'sharing_teacher')
        self.assertEqual(quest_origin.shared_by, 'sharing_teacher')
        self.assertEqual(quest_origin.deck_name, self.tenant.name)

    def _attribution_html(self, response):
        """The response's HTML with runs of whitespace collapsed to single spaces.

        The attribution is laid out over several template lines, so matching it as it
        appears in the source needs the indentation flattened first.

        Args:
            response (HttpResponse): the rendered page.

        Returns:
            str: the page HTML, whitespace-normalized.
        """
        return ' '.join(response.content.decode().split())

    def test_library_quest_list__attributes_a_shared_quest(self):
        """The Library's quest list names who shared each quest, and their deck."""
        self.client.post(reverse('library:export_quest', args=[self.local_quest.import_id]), data=AGREED_LICENCE)
        with library_schema_context():
            library_quest = Quest.objects.get(import_id=self.local_quest.import_id)
            library_quest.published = True
            library_quest.save()

        response = self.client.get(reverse('library:quest_list'))

        # the deck name follows "of" as plain text, not as a link: this viewer is staff of
        # their own deck, not of the Library, and other decks are closed to them, so a link
        # would be a dead end. (The deck's own name and URL appear in the page chrome too,
        # which is why this looks at the attribution itself rather than the whole page.)
        self.assertIn(
            f'Shared by sharing_teacher of {self.DECK_NAME}</small>', self._attribution_html(response)
        )
        self.assertFalse(response.context['viewer_is_library_staff'])

    def test_library_campaign_detail__attributes_a_shared_campaign(self):
        """The Library's campaign page carries the same attribution, unlinked."""
        self.client.post(reverse('library:export_category', args=[self.local_campaign.import_id]), data=AGREED_LICENCE)
        with library_schema_context():
            library_campaign = Category.objects.get(import_id=self.local_campaign.import_id)
            library_campaign.published = True
            library_campaign.save()

        response = self.client.get(
            reverse('library:category_detail_view', args=[self.local_campaign.import_id])
        )

        self.assertIn(
            f'Shared by sharing_teacher of {self.DECK_NAME} on ', self._attribution_html(response)
        )
        self.assertFalse(response.context['viewer_is_library_staff'])

    def test_library_quest_list__says_nothing_about_content_with_no_recorded_origin(self):
        """Content shared before origins were recorded is listed without a false attribution."""
        with library_schema_context():
            baker.make(Quest, name='An older library quest', published=True, archived=False)

        response = self.client.get(reverse('library:quest_list'))

        self.assertContains(response, 'An older library quest')
        self.assertNotContains(response, 'Shared by')


class ViewerIsLibraryStaffTests(LibraryTenantTestCaseMixin):
    """Who gets the deck name in an attribution rendered as a link (#2377).

    Only the Library's own staff, because every other deck is closed to everyone else and
    the link would be a dead end for them.
    """

    @classmethod
    def setUpTestData(cls):
        """One staff user and one student, to separate the two conditions the helper checks."""
        cls.staff = User.objects.create_user('library_admin', is_staff=True)
        cls.student = User.objects.create_user('a_student')

    def _request_from(self, user, tenant):
        """Build a bare request from a given user on a given deck.

        Args:
            user (User): who the request is from.
            tenant (Tenant): the deck serving the request, as the middleware would set it.

        Returns:
            HttpRequest: a GET request with `user` and `tenant` attached.
        """
        request = RequestFactory().get('/')
        request.user = user
        request.tenant = tenant
        return request

    def test_viewer_is_library_staff__true_for_staff_on_the_library_deck(self):
        """Staff browsing from the Library deck itself can open the decks they review."""
        self.assertTrue(viewer_is_library_staff(self._request_from(self.staff, self.library_tenant)))

    def test_viewer_is_library_staff__false_for_a_student_on_the_library_deck(self):
        """Being on the Library deck is not enough: reviewing content is a staff job."""
        self.assertFalse(viewer_is_library_staff(self._request_from(self.student, self.library_tenant)))

    def test_viewer_is_library_staff__false_for_staff_on_their_own_deck(self):
        """A teacher is staff of their own deck, not of the Library, so links stay off."""
        self.assertFalse(viewer_is_library_staff(self._request_from(self.staff, self.tenant)))

    def test_viewer_is_library_staff__ignores_the_schema_the_content_is_read_from(self):
        """The answer follows the deck serving the page, not a temporary schema switch.

        Both views ask this while inside `library_schema_context()`, so a connection-based
        answer would hand every teacher a link to a deck they cannot open.
        """
        request = self._request_from(self.staff, self.tenant)

        with library_schema_context():
            self.assertFalse(viewer_is_library_staff(request))


class ImportNextStepsTests(LibraryTenantTestCaseMixin):
    """A successful import says what is left to do, instead of leaving the quest invisible.

    An imported quest is an unpublished orphan: students can't see it and it isn't on the
    map. Saying so is the difference between "imported" and "usable" (#2377).
    """

    @classmethod
    def setUpTestData(cls):
        """Put a published quest and campaign in the Library, and make a teacher to import them."""
        with library_schema_context():
            cls.library_campaign = baker.make(Category, title='An importable campaign', published=True)
            cls.library_campaign_quest = baker.make(
                Quest, campaign=cls.library_campaign, published=True, archived=False
            )
            cls.library_quest = baker.make(Quest, name='An importable quest', published=True, archived=False)

        cls.test_teacher = User.objects.create_user('importing_teacher', is_staff=True)

    def setUp(self):
        """Log in as the importing teacher."""
        super().setUp()
        self.client.force_login(self.test_teacher)

    def test_import_quest_post__tells_the_user_to_publish_and_add_a_prerequisite(self):
        """The quest import message names both remaining steps."""
        response = self.client.post(
            reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True
        )

        imported = Quest.objects.get(import_id=self.library_quest.import_id)
        message = str(list(response.context['messages'])[0])
        # each step links to the page that performs it, rather than naming it and leaving
        # the reader to find it
        self.assertIn(f'href="{reverse("quests:quest_update", args=[imported.id])}">publish it</a>', message)
        self.assertIn(
            f'href="{reverse("quests:quest_prereqs_update", args=[imported.id])}">prerequisite</a>', message
        )

    def test_import_campaign_post__tells_the_user_to_publish_and_add_a_prerequisite(self):
        """The campaign import message names both remaining steps."""
        response = self.client.post(
            reverse('library:import_category', args=[self.library_campaign.import_id]), follow=True
        )

        imported = Category.objects.get(import_id=self.library_campaign.import_id)
        message = str(list(response.context['messages'])[0])
        self.assertIn(
            f'href="{reverse("quests:category_update", args=[imported.id])}">publish the campaign</a>', message
        )
        # the prerequisite belongs to one of its quests, so this one points at the campaign
        self.assertIn(f'href="{imported.get_absolute_url()}">prerequisite</a>', message)


class LibraryViewsOnPublicSchemaTests(LibraryTenantTestCaseMixin):
    """The Library is a per-deck feature and has no meaning on the public schema.

    There is a single urlconf, so `/library/...` resolves on the public tenant too,
    where `SiteConfig.get()` returns None. These views need the project's standard
    non-public guard ahead of anything that reads site config.
    """

    @classmethod
    def setUpTestData(cls):
        """Create a staff user to make the request."""
        cls.test_teacher = User.objects.create_user('public_schema_teacher', is_staff=True)

    @patch('tenant.views.connection', schema_name=get_public_schema_name())
    def test_library_views__404_on_the_public_schema(self, mock_connection):
        """Library URLs are not served from the public schema."""
        self.client.force_login(self.test_teacher)

        for url_name in ('library:quest_list', 'library:category_list'):
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 404)

    @patch('library.views.SiteConfig.get', return_value=None)
    def test_shared_library_enabled_view__404s_when_there_is_no_site_config(self, mock_get):
        """With no deck config there is no Shared Library either, so the check 404s.

        `SiteConfig.get()` returns None on the public schema. This check runs ahead
        of the non-public guard, so it has to handle that itself rather than raising
        AttributeError on a None config. Exercised against the decorator directly:
        going through the test client would render the 404 page, which calls
        `SiteConfig.get()` again and would fail on the patch rather than the guard.
        """
        wrapped = shared_library_enabled_view(lambda request: 'reached the view')

        with self.assertRaises(Http404):
            wrapped(RequestFactory().get('/'))


class ConflictingQuestCloneTests(LibraryTenantTestCaseMixin):
    """Copying a quest whose original is already in the Library must not carry local row ids.

    The copy used to be built with `deepcopy`, which kept `editor_id`,
    `specific_teacher_to_notify_id` and `common_data_id`: primary keys that mean
    something different in the Library's schema. Absent there, the export died on a
    ValidationError; present, the copy silently adopted a stranger's row.
    """

    @classmethod
    def setUpTestData(cls):
        """A local campaign whose quest also exists in the Library, plus local FK targets."""
        cls.test_teacher = User.objects.create_user('clone_teacher', is_staff=True)
        cls.local_editor = User.objects.create_user('clone_local_editor', is_staff=False)

    def _make_conflicting_campaign(self, **quest_kwargs):
        """Build a local campaign with one quest that already exists in the Library.

        Args:
            **quest_kwargs: extra field values for the local quest.

        Returns:
            tuple[Category, Quest]: the local campaign and its conflicting quest.
        """
        campaign = baker.make(Category, title=f"Conflict Campaign {uuid.uuid4().hex[:6]}")
        quest = baker.make(
            Quest, campaign=campaign, published=True, archived=False,
            name=f"Conflicted Quest {uuid.uuid4().hex[:6]}", **quest_kwargs
        )
        with library_schema_context():
            baker.make(Quest, import_id=quest.import_id, published=False,
                       name=f"Library copy {uuid.uuid4().hex[:6]}")
        return campaign, quest

    def _library_clone_of(self, quest):
        """Return the Library copy of `quest`: same campaign, different import_id.

        Args:
            quest (Quest): the local quest that was copied.

        Returns:
            Quest: the copy created in the Library schema.
        """
        return Quest.objects.all_including_archived().exclude(import_id=quest.import_id).get(
            campaign__import_id=quest.campaign.import_id
        )

    def test_export_campaign_and_copy_quests__succeeds_when_the_quest_has_an_editor(self):
        """A conflicting quest with local user FKs exports instead of raising ValidationError."""
        campaign, quest = self._make_conflicting_campaign(
            editor=self.local_editor, specific_teacher_to_notify=self.test_teacher
        )

        export_campaign_and_copy_quests(
            source_schema=self.tenant.schema_name, campaign_import_id=campaign.import_id
        )

        with library_schema_context():
            clone = self._library_clone_of(quest)
            self.assertIsNone(clone.editor)
            self.assertIsNone(clone.specific_teacher_to_notify)

    def test_export_campaign_and_copy_quests__does_not_adopt_a_library_row_at_the_same_pk(self):
        """The copy drops common_data rather than pointing at whatever shares that pk."""
        with library_schema_context():
            library_common = baker.make(CommonData, title="LIBRARY BLURB")

        local_common = baker.make(CommonData, title="LOCAL BLURB")
        campaign, quest = self._make_conflicting_campaign(common_data=local_common)

        export_campaign_and_copy_quests(
            source_schema=self.tenant.schema_name, campaign_import_id=campaign.import_id
        )

        with library_schema_context():
            clone = self._library_clone_of(quest)
            self.assertIsNone(clone.common_data)
            # the Library's own row is untouched by the export
            library_common.refresh_from_db()
            self.assertEqual(library_common.title, "LIBRARY BLURB")

    def test_export_campaign_and_copy_quests__copy_keeps_the_quest_content(self):
        """Dropping the cross-schema FKs must not gut the copy: its content still travels."""
        campaign, quest = self._make_conflicting_campaign(
            xp=42, instructions="<p>Do the thing</p>", short_description="A conflicted quest",
        )

        export_campaign_and_copy_quests(
            source_schema=self.tenant.schema_name, campaign_import_id=campaign.import_id
        )

        with library_schema_context():
            clone = self._library_clone_of(quest)
            self.assertEqual(clone.xp, 42)
            # the quest_manager signal re-indents saved HTML, so match on the content
            self.assertIn("Do the thing", clone.instructions)
            self.assertEqual(clone.short_description, "A conflicted quest")
            self.assertFalse(clone.published)
            self.assertNotEqual(clone.import_id, quest.import_id)
            self.assertIn("(Exported on", clone.name)

    def test_clone_quests_into_library__returns_none_when_there_is_nothing_to_copy(self):
        """A campaign with no conflicts skips the copy step entirely."""
        self.assertIsNone(clone_quests_into_library(source_schema=self.tenant.schema_name, quests=[]))

    def test_build_library_clone_name__falls_back_to_a_numbered_suffix(self):
        """A taken dated name pushes the next copy on to a numbered suffix."""
        dated = f"Quest A (Exported on {date.today()})"

        self.assertEqual(build_library_clone_name("Quest A", set()), dated)
        self.assertEqual(
            build_library_clone_name("Quest A", {dated}),
            f"Quest A (Exported on {date.today()}) #1",
        )

    def test_build_library_clone_name__stays_within_the_field_max_length(self):
        """A long source name is truncated so the suffixed name still fits."""
        max_len = Quest._meta.get_field('name').max_length

        name = build_library_clone_name("x" * max_len, set())

        self.assertLessEqual(len(name), max_len)
        self.assertIn("(Exported on", name)

    def test_export_campaign_and_copy_quests__copy_does_not_collide_with_an_archived_name(self):
        """The naming loop consults archived Library quests, which the default manager hides."""
        campaign, quest = self._make_conflicting_campaign()
        with library_schema_context():
            # Claim the name the copy would otherwise take, on an archived quest
            baker.make(Quest, name=build_library_clone_name(quest.name, set()), archived=True)

        export_campaign_and_copy_quests(
            source_schema=self.tenant.schema_name, campaign_import_id=campaign.import_id
        )

        with library_schema_context():
            clone = self._library_clone_of(quest)
            self.assertTrue(clone.name.endswith("#1"), f"expected a numbered suffix, got {clone.name!r}")
