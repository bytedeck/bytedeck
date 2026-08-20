import uuid
from copy import deepcopy
from datetime import date
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages import get_messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection
from django.http import Http404
from django.template.loader import get_template
from django.test import RequestFactory
from django.urls import reverse
from django_tenants.utils import get_public_schema_name, schema_exists
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from library.utils import get_library_schema_name, library_schema_context
from library.models import ContentOrigin
from library.views import ExportQuestView, LibraryQuestListView, shared_library_enabled_view, viewer_is_library_staff
from library.importer import import_quest_to, import_campaign_to
from library.transfer import LibraryTransferError
from library.exporter import (
    build_library_clone_name,
    clone_quests_into_library,
    export_campaign_and_copy_quests,
    export_campaign_to_library,
    export_quest_to_library,
)
from model_bakery import baker
from notifications.models import Notification
from courses.models import Rank
from prerequisites.models import Prereq
from quest_manager.models import Category, CommonData, Quest
from questions.models import Question
from siteconfig.models import SiteConfig
from utilities.html import textify
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

    def _message_texts(self, response):
        """The messages queued for the user by a request.

        Args:
            response (HttpResponse): the response to read the message storage from.

        Returns:
            list[str]: the message bodies.
        """
        return [str(message) for message in get_messages(response.wsgi_request)]

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

    def test_import_quest__post_when_quest_exists_locally_is_refused(self):
        """POSTing to import a quest whose import_id already exists on the local deck imports nothing.

        The refusal is a redirect carrying an explanation rather than a 403, since the deck
        already having the quest is a conflict and not a permission problem (#2373).
        """
        self.client.force_login(self.test_teacher)

        local_quest = baker.make(Quest)
        with library_schema_context():
            library_quest = baker.make(Quest, import_id=local_quest.import_id)

        url = reverse('library:import_quest', args=[library_quest.import_id])
        response = self.client.post(url)

        self.assertRedirects(response, reverse('library:quest_list'))
        # the local quest was not duplicated by the refused import
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
        # captureOnCommitCallbacks: the email waits for the push to commit, so that a
        # rolled-back push cannot invite anyone to review it (#2372). Under TestCase the
        # surrounding transaction never commits, so the callbacks are run here instead.
        with self.captureOnCommitCallbacks(execute=True):
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

    @patch("tenant.tasks.send_email_message.apply_async")
    def test_export_post__review_email_reads_as_paragraphs(self, mock_apply_async):
        """The review email arrives as separate paragraphs, not one run-on block.

        Its template is rendered into the shared HTML wrapper and sent as the text/html
        part, with the plain-text part derived from that by `textify`. Bare newlines
        collapse in both, so the content's name ran straight into the sentence after it,
        which is the part a reviewer actually needs to read (#2371).
        """
        with library_schema_context():
            User.objects.create_user('librarian', email='librarian@example.com', is_staff=True)

        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()
        self.client.force_login(self.test_teacher)

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('library:export_quest', args=[self.local_quest.import_id]), data=AGREED_LICENCE)

        _, message, _ = mock_apply_async.call_args.kwargs['args']

        # The name stands on its own, so it cannot run into the sentence that follows it.
        self.assertIn(f'<p><strong>{self.local_quest.name}</strong></p>', message)
        # and the paragraph after it starts a block of its own rather than continuing the line.
        self.assertIn('<p>It has been added to the Library', message)
        # The plain-text part is derived from this HTML, so the breaks have to survive it.
        self.assertIn(self.local_quest.name, textify(message))
        self.assertNotIn(f'{self.local_quest.name} It has been added', textify(message))

    def test_export_post__review_email_carries_the_shared_footer(self):
        """The review email closes with the same footer as every other platform email (#2371)."""
        message = get_template("library/email/content_pushed.html").render({
            "sharer": self.test_teacher,
            "content_type": "quest",
            "content_name": "A Quest",
            "review_url": "https://library.test.com/quests/1/",
            "source_deck_url": "https://tenant.test.com",
        })

        self.assertIn('contact@bytedeck.com', message)
        self.assertNotIn('ByteDeck Library</p>', message)

    def test_export_post__refused_if_quest_already_exists_in_library(self):
        """A POST to export a quest already in the Library is refused with an explanation.

        A redirect rather than a 403: the Library having it already is a conflict, not
        something the sharer lacks permission for (#2373).
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()

        self.client.force_login(self.test_teacher)

        url = reverse("library:export_quest", kwargs={"quest_import_id": str(self.shared_quest.import_id)})
        response = self.client.post(url, data=AGREED_LICENCE)

        self.assertRedirects(response, reverse('quests:quests'))


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

    def test_import_campaign__post_when_campaign_exists_locally_is_refused(self):
        """POSTing to import a campaign whose import_id already exists on the local deck imports nothing.

        The refusal is a redirect carrying an explanation rather than a 403, since the deck
        already having the campaign is a conflict and not a permission problem (#2373).
        """
        self.client.force_login(self.test_teacher)

        with library_schema_context():
            library_category = baker.make(Category)
        # a local campaign already shares the import_id
        baker.make(Category, import_id=library_category.import_id)

        import_url = reverse('library:import_category', args=[library_category.import_id])
        response = self.client.post(import_url)

        self.assertRedirects(response, reverse('library:category_list'))
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

    def test_export_post__refused_if_campaign_exists(self):
        """A POST to export a campaign already in the Library is refused with an explanation.

        A redirect rather than a 403: the Library having it already is a conflict, not
        something the sharer lacks permission for (#2373).
        """
        self.config.allow_staff_export = True
        self.config.full_clean()
        self.config.save()
        self.client.force_login(self.test_teacher)

        url = reverse('library:export_category', kwargs={'campaign_import_id': str(self.shared_category.import_id)})
        response = self.client.post(url, data=AGREED_LICENCE)
        self.assertRedirects(response, reverse('quests:categories'))

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
        # captureOnCommitCallbacks: see the quest export test above.
        with self.captureOnCommitCallbacks(execute=True):
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

    def test_export_quest_to_library__name_already_taken_in_the_library_names_the_quest(self):
        """A quest whose name the Library already holds fails with that name in the message."""
        with library_schema_context():
            baker.make(Quest, name="Taken In The Library", published=True)

        quest = baker.make(Quest, name="Taken In The Library", published=True)

        with self.assertRaisesMessage(LibraryTransferError, "Taken In The Library"):
            export_quest_to_library(source_schema=self.tenant.schema_name, quest_import_id=quest.import_id)

    def test_clone_quests_into_library__database_failure_is_reported_as_a_transfer_error(self):
        """A constraint that only the database can see still reaches the caller readably.

        `full_clean` catches the failures that can be checked in Python, so this covers the
        branch below it: a database-level error is reported as a `LibraryTransferError`
        rather than escaping as a bare `IntegrityError`. The patch is scoped to the copy
        itself, since the fixture above it has to be able to save normally.
        """
        quest = baker.make(Quest, published=True)

        with patch("library.transfer.Quest.save", side_effect=IntegrityError("duplicate key")):
            with self.assertRaises(LibraryTransferError):
                clone_quests_into_library(source_schema=self.tenant.schema_name, quests=[quest])

    def test_export_campaign_to_library__no_published_quests_raises_validation_error(self):
        """Exporting a campaign that has no published quests (and no skip list) is rejected with a ValidationError."""
        campaign = baker.make(Category)
        baker.make(Quest, campaign=campaign, published=False)
        with self.assertRaisesMessage(ValidationError, "Cannot export a campaign without any published quests."):
            export_campaign_to_library(source_schema=self.tenant.schema_name, campaign_import_id=campaign.import_id)

    def test_export_campaign_to_library__name_already_taken_in_the_library_names_the_quest(self):
        """A campaign carrying a quest whose name the Library holds fails with that name."""
        with library_schema_context():
            baker.make(Quest, name="Clashing Campaign Quest", published=True)

        campaign = baker.make(Category)
        baker.make(Quest, name="Clashing Campaign Quest", campaign=campaign, published=True)

        with self.assertRaisesMessage(LibraryTransferError, "Clashing Campaign Quest"):
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
        # Both steps live on the campaign's own page: the publish button there is the one
        # that publishes the quests too, and the quests are listed there so the first can
        # be given a prerequisite (#2533)
        self.assertIn(f'href="{imported.get_absolute_url()}">publish the campaign</a>', message)
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

    def test_clone_quests_into_library__returns_nothing_when_there_is_nothing_to_copy(self):
        """A campaign with no conflicts skips the copy step entirely."""
        result = clone_quests_into_library(source_schema=self.tenant.schema_name, quests=[])

        self.assertEqual(result.quests, [])
        self.assertEqual(result.unmet_prereqs, [])

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

class LibraryImportNameCollisionTests(LibraryTenantTestCaseMixin):
    """Importing a quest whose name this deck already uses for something else.

    Quest names are unique per deck, so the arriving copy is renamed rather than refused:
    a teacher should not have to go and rename their own quest before they can import
    (#2364), and one clashing name should not cost a whole campaign its import (#2397).
    """

    @classmethod
    def setUpTestData(cls):
        """Publish a quest and a campaign in the Library, and a staff user to import them."""
        with library_schema_context():
            cls.library_campaign = baker.make(Category, published=True)
            cls.library_quest = baker.make(
                Quest, name="Contested Name", campaign=cls.library_campaign, published=True,
            )

        cls.test_teacher = User.objects.create_user('collision_teacher', is_staff=True)

    def test_import_quest__gives_the_arriving_copy_a_name_of_its_own(self):
        """The import succeeds, and both quests exist afterwards under different names."""
        local = baker.make(Quest, name="Contested Name")
        self.client.force_login(self.test_teacher)

        self.client.post(reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True)

        imported = Quest.objects.all_including_archived().get(import_id=self.library_quest.import_id)
        self.assertNotEqual(imported.pk, local.pk)
        self.assertTrue(imported.name.startswith("Contested Name (Imported on "))

    def test_import_quest__leaves_the_teachers_own_quest_untouched(self):
        """Renaming happens to the arriving copy, never to what the deck already had."""
        local = baker.make(Quest, name="Contested Name")
        self.client.force_login(self.test_teacher)

        self.client.post(reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True)

        local.refresh_from_db()
        self.assertEqual(local.name, "Contested Name")

    def test_import_quest__tells_the_teacher_the_copy_arrived_under_another_name(self):
        """A quest that is not called what the Library said it was called is worth saying.

        Otherwise the teacher goes looking for the name they clicked on and finds their own
        quest instead, with the import apparently having done nothing.
        """
        baker.make(Quest, name="Contested Name")
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True,
        )

        imported = Quest.objects.all_including_archived().get(import_id=self.library_quest.import_id)
        self.assertTrue(
            any(imported.name in text for text in self._message_texts(response)),
            f"expected the new name to be given, got {self._message_texts(response)}",
        )

    def test_import_quest__says_nothing_about_renaming_when_the_name_was_free(self):
        """An import with no clash keeps the message to the two steps that always apply."""
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True,
        )

        self.assertFalse(
            any("already had a quest" in text for text in self._message_texts(response)),
            f"expected no rename message, got {self._message_texts(response)}",
        )

    def test_import_category__imports_the_whole_campaign_despite_one_clashing_name(self):
        """The campaign and every one of its quests arrive; only the clashing one is renamed."""
        with library_schema_context():
            baker.make(Quest, name="Uncontested Name", campaign=self.library_campaign, published=True)
        baker.make(Quest, name="Contested Name")
        self.client.force_login(self.test_teacher)

        self.client.post(reverse('library:import_category', args=[self.library_campaign.import_id]), follow=True)

        self.assertTrue(Category.objects.filter(import_id=self.library_campaign.import_id).exists())
        imported = Quest.objects.all_including_archived().get(import_id=self.library_quest.import_id)
        self.assertTrue(imported.name.startswith("Contested Name (Imported on "))
        self.assertTrue(Quest.objects.all_including_archived().filter(name="Uncontested Name").exists())

    def test_import_quest__names_the_clash_on_the_confirmation_page(self):
        """The teacher sees the clash before clicking Import, not after.

        The Library page shows what is on offer, not what is already on their own deck, so
        this is the one thing they cannot check for themselves.
        """
        baker.make(Quest, name="Contested Name")
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:import_quest', args=[self.library_quest.import_id]))

        self.assertContains(response, "cannot share a name")
        self.assertContains(response, "Contested Name")

    def test_import_quest__confirmation_page_stays_quiet_when_no_name_clashes(self):
        """A quest whose name is free gets the plain confirmation page."""
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:import_quest', args=[self.library_quest.import_id]))

        self.assertNotContains(response, "cannot share a name")

    def test_import_category__names_the_clash_on_the_confirmation_page(self):
        """The campaign confirmation page names the quests that will arrive renamed."""
        baker.make(Quest, name="Contested Name")
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:import_category', args=[self.library_campaign.import_id]))

        self.assertContains(response, "cannot share a name")
        self.assertContains(response, "Contested Name")

    def test_import_quest__reports_a_failure_that_renaming_cannot_fix(self):
        """A write the database refuses still redirects with an explanation, not a 500.

        Renaming answers the name clash and nothing else, so the failure path stays: the
        teacher is told which quest could not be copied and that nothing was added.
        """
        self.client.force_login(self.test_teacher)

        with patch.object(Quest, 'save', side_effect=IntegrityError("duplicate key value")):
            response = self.client.post(
                reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any("nothing was added to your deck" in text for text in self._message_texts(response)),
            f"expected a failure message, got {self._message_texts(response)}",
        )
        self.assertFalse(
            Quest.objects.all_including_archived().filter(import_id=self.library_quest.import_id).exists()
        )

    def test_import_category__reports_a_failure_that_renaming_cannot_fix(self):
        """A campaign whose quest the database refuses is discarded whole, and says so.

        The campaign import stays all-or-nothing for everything except the name clash: a
        half-imported campaign would leave the deck holding quests whose prerequisites point
        at the ones that never arrived.
        """
        self.client.force_login(self.test_teacher)

        with patch.object(Quest, 'save', side_effect=IntegrityError("duplicate key value")):
            response = self.client.post(
                reverse('library:import_category', args=[self.library_campaign.import_id]), follow=True,
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any("nothing was added to your deck" in text for text in self._message_texts(response)),
            f"expected a failure message, got {self._message_texts(response)}",
        )
        self.assertFalse(Category.objects.filter(import_id=self.library_campaign.import_id).exists())


class LibraryImportPrereqBehaviourTests(LibraryTenantTestCaseMixin):
    """What happens to a quest's prerequisites when the importing deck does not have them.

    Imported content is a self-contained package: the importing teacher places it into
    their own map and sets their own prerequisites, so a prerequisite that did not travel is not
    something they need telling about. It is the sharer's business, and is warned about on
    the push instead (see `LibrarySharerWarningTests`).
    """

    @classmethod
    def setUpTestData(cls):
        """Publish a Library quest requiring another quest that is not being imported."""
        with library_schema_context():
            cls.prereq_target = baker.make(Quest, name="Finish The Prologue", published=True)
            cls.library_quest = baker.make(Quest, name="Chapter Two", published=True)
            Prereq.add_simple_prereq(cls.library_quest, cls.prereq_target)

        cls.test_teacher = User.objects.create_user('unmet_prereq_teacher', is_staff=True)

    def test_import_quest__arrives_with_no_prerequisite_when_the_target_is_missing(self):
        """A quest whose prerequisite target this deck does not have arrives with none."""
        self.client.force_login(self.test_teacher)

        self.client.post(reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True)

        imported = Quest.objects.all_including_archived().get(import_id=self.library_quest.import_id)
        self.assertEqual(list(imported.prereqs()), [])

    def test_import_quest__rebuilds_a_prerequisite_the_deck_already_has(self):
        """A deck holding the target gets the prerequisite rebuilt rather than dropped."""
        import_quest_to(destination_schema=connection.schema_name, quest_import_id=self.prereq_target.import_id)
        self.client.force_login(self.test_teacher)

        self.client.post(reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True)

        imported = Quest.objects.all_including_archived().get(import_id=self.library_quest.import_id)
        self.assertEqual([p.get_prereq().name for p in imported.prereqs()], ["Finish The Prologue"])

    def test_import_quest__re_importing_does_not_duplicate_an_existing_prerequisite(self):
        """Importing the same quest twice refreshes it without stacking up its prerequisite again.

        Re-importing is how a deck picks up an updated version of Library content, so it
        happens to quests that already have their prerequisites wired up.
        """
        import_quest_to(destination_schema=connection.schema_name, quest_import_id=self.prereq_target.import_id)
        import_quest_to(destination_schema=connection.schema_name, quest_import_id=self.library_quest.import_id)

        import_quest_to(destination_schema=connection.schema_name, quest_import_id=self.library_quest.import_id)

        imported = Quest.objects.all_including_archived().get(import_id=self.library_quest.import_id)
        self.assertEqual([p.get_prereq().name for p in imported.prereqs()], ["Finish The Prologue"])

    def test_import_quest__tells_the_importer_only_what_they_have_to_do_next(self):
        """The import message covers publishing and prerequisites, and nothing about what was lost.

        Everything the Library could not carry is reported to the sharer on the push. The
        importer is told the two things they have to do, which is all that is theirs to act
        on (#2452).
        """
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True,
        )

        texts = self._message_texts(response)
        self.assertTrue(any("publish" in text.lower() and "prerequisite" in text.lower() for text in texts))
        self.assertFalse(
            any("Finish The Prologue" in text for text in texts),
            f"the importer should not be told about prerequisites that did not travel, got {texts}",
        )


class LibraryShareRefusalTests(LibraryTenantTestCaseMixin):
    """A share the Library would reject is refused with a reason, not a 500.

    A quest name and a campaign title are unique per schema, so content whose name is
    already taken in the Library cannot be written there. The sharer cannot see that from
    their own deck: the Library is another schema, and their own deck's pages say nothing
    about what is in it. Refusing with a reason is the only thing standing between them
    and a failure they cannot interpret, after they have agreed to the licence (#2531).
    """

    @classmethod
    def setUpTestData(cls):
        """Create a staff user to share content from this deck."""
        cls.test_teacher = User.objects.create_user('share_refusal_teacher', is_staff=True)

    def setUp(self):
        """Let any staff user share, and sign the teacher in."""
        super().setUp()
        config = SiteConfig.get()
        config.allow_staff_export = True
        config.save()
        self.client.force_login(self.test_teacher)

    def _take_the_name_in_the_library(self, name):
        """Put an unrelated quest into the Library under `name`.

        A different quest, not the one being shared: same name, its own import_id, which
        is what makes it a clash rather than the same content arriving again.

        Args:
            name (str): the quest name to occupy.
        """
        with library_schema_context():
            baker.make(Quest, name=name, published=True)

    def test_export_quest__get_warns_that_the_name_is_taken(self):
        """The share confirmation page names the clash before the licence is agreed to.

        Refusing at this point costs the teacher a rename; refusing after the POST costs
        them the same rename plus a server error page they cannot interpret (#2531).
        """
        local = baker.make(Quest, name="Photoshop Basics", published=True)
        self._take_the_name_in_the_library("Photoshop Basics")

        response = self.client.get(reverse('library:export_quest', args=[local.import_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already has a different quest called")
        # No licence form on a page that cannot go through.
        self.assertNotContains(response, 'id="export-form"')

    def test_export_quest__post_is_refused_with_a_message(self):
        """Submitting a share whose name is taken redirects with the reason (#2531).

        Nothing reaches the Library, and the message names the quest so the teacher knows
        which one to rename.
        """
        local = baker.make(Quest, name="Photoshop Basics", published=True)
        self._take_the_name_in_the_library("Photoshop Basics")

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertEqual(response.status_code, 200)
        texts = self._message_texts(response)
        self.assertTrue(
            any("Photoshop Basics" in text and "could not be completed" in text for text in texts),
            f"expected a refusal naming the quest, got {texts}",
        )
        with library_schema_context():
            self.assertFalse(Quest.objects.filter(import_id=local.import_id).exists())

    def test_export_quest__a_clash_arriving_mid_push_is_still_refused(self):
        """A failure the pre-check could not have seen is refused, not raised (#2531).

        The guard runs before the write, so between the two another deck can take the name.
        Patching the push to raise is how that race is reached deterministically: the point
        is that the exception is turned into a message rather than escaping as a 500.
        """
        local = baker.make(Quest, name="Racing The Library", published=True)

        with patch(
            'library.views.export_quest_to_library',
            side_effect=LibraryTransferError("'Racing The Library' could not be copied: name: already exists."),
        ):
            response = self.client.post(
                reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
            )

        self.assertEqual(response.status_code, 200)
        texts = self._message_texts(response)
        self.assertTrue(
            any("Racing The Library" in text and "could not be completed" in text for text in texts),
            f"expected the raised failure to be reported, got {texts}",
        )

    def test_export_quest__the_refusal_escapes_markup_in_the_clashing_name(self):
        """A clashing name carrying HTML is escaped in the refusal message.

        The name in this message comes from the *Library*, so it was written on a deck
        other than the one reading it. That makes it the one part of the message its
        reader has no control over, and worth pinning: messages are rendered through
        `_message_body.html`, which escapes a plain string and only lets markup through
        when it was built with `format_html` (#2498).
        """
        local = baker.make(Quest, name="Clean Quest Name", published=True)
        self._take_the_name_in_the_library("Clean Quest Name")
        with library_schema_context():
            Quest.objects.filter(name="Clean Quest Name").update(name="<img src=x onerror=alert(1)>")
        Quest.objects.filter(pk=local.pk).update(name="<img src=x onerror=alert(1)>")

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertNotContains(response, "<img src=x onerror=alert(1)>")
        self.assertContains(response, "&lt;img src=x onerror=alert(1)&gt;")

    def test_export_campaign__post_is_refused_when_the_title_is_taken(self):
        """A campaign whose title the Library already uses is refused, not 500 (#2534).

        The clash is on `Category.title`, which is unique per schema, so `full_clean`
        rejects the write and the refusal has to come from the view rather than the page.
        """
        campaign = baker.make(Category, title="Digital Citizenship", published=True)
        quest = baker.make(Quest, name="A Quest Of Its Own", campaign=campaign, published=True)
        with library_schema_context():
            baker.make(Category, title="Digital Citizenship", published=True)

        response = self.client.post(
            reverse('library:export_category', args=[campaign.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertEqual(response.status_code, 200)
        texts = self._message_texts(response)
        self.assertTrue(
            any("Digital Citizenship" in text and "could not be completed" in text for text in texts),
            f"expected a refusal naming the campaign, got {texts}",
        )
        with library_schema_context():
            self.assertFalse(Category.objects.filter(import_id=campaign.import_id).exists())
            self.assertFalse(Quest.objects.filter(import_id=quest.import_id).exists())

    def test_export_campaign__post_is_refused_when_a_quest_name_is_taken(self):
        """A campaign carrying a quest whose name is taken is refused as a whole (#2534).

        The push is atomic, so a clash on one quest stops the campaign: better to say which
        name is in the way than to leave half of it in the Library.
        """
        campaign = baker.make(Category, title="Soldering Skills", published=True)
        baker.make(Quest, name="Tin Your Iron", campaign=campaign, published=True)
        self._take_the_name_in_the_library("Tin Your Iron")

        response = self.client.post(
            reverse('library:export_category', args=[campaign.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertEqual(response.status_code, 200)
        texts = self._message_texts(response)
        self.assertTrue(
            any("Tin Your Iron" in text for text in texts),
            f"expected a refusal naming the quest, got {texts}",
        )
        with library_schema_context():
            self.assertFalse(Category.objects.filter(import_id=campaign.import_id).exists())

    def test_export_campaign__post_with_no_published_quests_is_refused(self):
        """POSTing a share for a campaign with nothing publishable is refused (#2534).

        The button for this is disabled in the UI, but the URL is not, so a stale tab or a
        resubmit reached the exporter and raised. Nothing about a disabled button stops a
        POST.
        """
        campaign = baker.make(Category, title="Empty Campaign", published=True)

        response = self.client.post(
            reverse('library:export_category', args=[campaign.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertEqual(response.status_code, 200)
        texts = self._message_texts(response)
        self.assertTrue(
            any("could not be completed" in text for text in texts),
            f"expected a refusal rather than a server error, got {texts}",
        )


class LibrarySharerWarningTests(LibraryTenantTestCaseMixin):
    """What the Library tells the sharer it could not carry.

    Content shared to the Library is meant to be a self-contained package, so the losses
    belong to the person pushing it: they are the only one who can widen what they share,
    and the only one who can still see what is missing (#2399, #2442, #2450).
    """

    @classmethod
    def setUpTestData(cls):
        """Create a staff user to share content from this deck."""
        cls.test_teacher = User.objects.create_user('sharer_warning_teacher', is_staff=True)

    def _allow_staff_export(self):
        """Let a staff user share, rather than only the deck owner."""
        config = SiteConfig.get()
        config.allow_staff_export = True
        config.save()

    def test_export_quest__warns_the_sharer_that_a_prerequisite_could_not_travel(self):
        """Sharing a quest with a rank prerequisite tells the sharer the copy arrives without it.

        This is the only place the loss is visible. The Library row simply has no
        prerequisite, so nobody downstream can tell it ever had one (#2399, #2450).
        """
        rank = baker.make(Rank, name="Digital Novice")
        local = baker.make(Quest, name="Locally Restricted Quest", published=True)
        Prereq.add_simple_prereq(local, rank)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertTrue(
            any("Digital Novice" in text for text in self._message_texts(response)),
            f"expected the sharer to be told, got {self._message_texts(response)}",
        )

    def test_export_quest__escapes_markup_in_a_lost_prerequisites_name(self):
        """A markup-bearing name reaches the sharer's warning as text, not as markup.

        The messages block renders through `|safe`, so the warning must pre-escape the
        names it interpolates; otherwise a rank or quest named with a tag would run as
        HTML for whoever shares content that requires it.
        """
        rank = baker.make(Rank, name="<b>Sneaky Rank</b>")
        local = baker.make(Quest, name="Quest Requiring Markup", published=True)
        Prereq.add_simple_prereq(local, rank)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        texts = self._message_texts(response)
        self.assertTrue(any("&lt;b&gt;Sneaky Rank&lt;/b&gt;" in text for text in texts), texts)
        self.assertFalse(any("<b>Sneaky Rank</b>" in text for text in texts), texts)

    def test_export_quest__escapes_markup_in_a_lost_alternatives_name(self):
        """The lost-alternative warning pre-escapes names the same way (issue #2549)."""
        main = baker.make(Quest, name="Shareable Main Requirement", published=True)
        rank = baker.make(Rank, name="<i>Sneaky Alternative</i>")
        local = baker.make(Quest, name="Quest With Markup Alternative", published=True)
        prereq = Prereq.add_simple_prereq(local, main)
        prereq.or_prereq_content_type = ContentType.objects.get_for_model(rank)
        prereq.or_prereq_object_id = rank.id
        prereq.full_clean()
        prereq.save()
        export_quest_to_library(source_schema=connection.schema_name, quest_import_id=main.import_id)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        texts = self._message_texts(response)
        self.assertTrue(any("&lt;i&gt;Sneaky Alternative&lt;/i&gt;" in text for text in texts), texts)
        self.assertFalse(any("<i>Sneaky Alternative</i>" in text for text in texts), texts)

    def test_export_quest__pluralises_the_missing_prerequisites_warning(self):
        """Two prerequisites that cannot travel get plural wording, one warning.

        A single missing prerequisite reads "One thing did not travel"; with several the
        message switches to "Some things" and "prerequisites", so the grammar matches
        however many names it lists.
        """
        local = baker.make(Quest, name="Quest With Two Rank Prereqs", published=True)
        for rank_name in ("First Missing Rank", "Second Missing Rank"):
            Prereq.add_simple_prereq(local, baker.make(Rank, name=rank_name))
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        texts = self._message_texts(response)
        plural = [text for text in texts if "Some things did not travel" in text]
        self.assertEqual(len(plural), 1, texts)
        self.assertIn("'First Missing Rank', 'Second Missing Rank'", plural[0])
        self.assertIn("as prerequisites", plural[0])

    def test_export_quest__pluralises_the_lost_alternatives_warning(self):
        """Two prerequisites each losing their alternative get plural wording, one warning.

        A single lost alternative reads "A prerequisite kept its main requirement"; with
        several the message switches to "Some prerequisites" and "alternatives", so the
        grammar matches however many names it lists.
        """
        main1 = baker.make(Quest, name="First Main Requirement", published=True)
        main2 = baker.make(Quest, name="Second Main Requirement", published=True)
        local = baker.make(Quest, name="Quest With Two Narrowed Prereqs", published=True)
        for main, rank_name in ((main1, "First Lost Route"), (main2, "Second Lost Route")):
            rank = baker.make(Rank, name=rank_name)
            prereq = Prereq.add_simple_prereq(local, main)
            prereq.or_prereq_content_type = ContentType.objects.get_for_model(rank)
            prereq.or_prereq_object_id = rank.id
            prereq.full_clean()
            prereq.save()
            export_quest_to_library(source_schema=connection.schema_name, quest_import_id=main.import_id)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        texts = self._message_texts(response)
        plural = [text for text in texts if "Some prerequisites kept their main requirement" in text]
        self.assertEqual(len(plural), 1, texts)
        self.assertIn("'First Lost Route', 'Second Lost Route'", plural[0])
        self.assertIn("alternatives too", plural[0])

    def test_export_quest__stays_quiet_when_the_prerequisite_is_already_in_the_library(self):
        """No warning when the Library already holds the quest this one requires.

        A single-quest share carries only that quest, so its prerequisite resolves in the
        Library only if it is already there. Sharing the target first is what makes that
        true.
        """
        target = baker.make(Quest, name="Shareable Requirement", published=True)
        local = baker.make(Quest, name="Quest With A Shareable Requirement", published=True)
        Prereq.add_simple_prereq(local, target)
        export_quest_to_library(source_schema=connection.schema_name, quest_import_id=target.import_id)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertFalse(
            any("did not travel" in text for text in self._message_texts(response)),
            f"expected no warning, got {self._message_texts(response)}",
        )

    def test_export_quest__warns_the_sharer_that_an_or_alternative_could_not_travel(self):
        """Losing only a prerequisite's OR alternative gets its own warning, not the missing-prerequisite one.

        The prerequisite itself survives, so the copy arrives stricter than written, with
        one of the ways to meet it gone. Saying the copy is missing its prerequisite for
        that case would point the teacher at the wrong problem, so the alternative gets a
        message of its own instead (#2549).
        """
        main = baker.make(Quest, name="Shareable Requirement", published=True)
        local = baker.make(Quest, name="Quest With A Narrower Copy", published=True)
        prereq = Prereq.add_simple_prereq(local, main)
        rank = baker.make(Rank, name="Digital Novice")
        prereq.or_prereq_content_type = ContentType.objects.get_for_model(rank)
        prereq.or_prereq_object_id = rank.id
        prereq.full_clean()
        prereq.save()
        export_quest_to_library(source_schema=connection.schema_name, quest_import_id=main.import_id)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        texts = self._message_texts(response)
        self.assertTrue(
            any("lost its OR alternative" in text and "Digital Novice" in text for text in texts),
            f"expected the alternative to be named in its own warning, got {texts}",
        )
        self.assertFalse(
            any("One thing did not travel" in text for text in texts),
            f"expected no missing-prerequisite warning when only the alternative was lost, got {texts}",
        )

    def test_export_quest__warns_the_sharer_that_the_general_info_block_stays_behind(self):
        """Sharing a quest that uses a General Info block says the copy arrives without it.

        `CommonData` has no `import_id`, so there is no key that means the same block in
        another deck's schema and it cannot travel. That is correct, but the quest arrives
        missing a panel its instructions may refer to, so the sharer is told (#2398).
        """
        common = CommonData.objects.create(title="Lab Safety Rules", instructions="<p>goggles on</p>")
        local = baker.make(Quest, name="Quest With Shared Preamble", published=True, common_data=common)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertTrue(
            any("Lab Safety Rules" in text for text in self._message_texts(response)),
            f"expected the General Info block to be named, got {self._message_texts(response)}",
        )

    def test_export_quest__stays_quiet_when_the_quest_uses_no_general_info(self):
        """A quest with no shared preamble shares without that warning."""
        local = baker.make(Quest, name="Self Contained Quest", published=True, common_data=None)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertFalse(
            any("General Info" in text for text in self._message_texts(response)),
            f"expected no warning, got {self._message_texts(response)}",
        )

    def test_export_category__warns_once_for_a_block_shared_by_several_quests(self):
        """A campaign whose quests share one General Info block names it a single time.

        The block is deduplicated, since naming the same rubric once per quest would bury
        the message it belongs to.
        """
        common = CommonData.objects.create(title="Marking Rubric", instructions="<p>how marks work</p>")
        campaign = baker.make(Category, published=True)
        baker.make(Quest, name="Rubric Quest One", campaign=campaign, published=True, common_data=common)
        baker.make(Quest, name="Rubric Quest Two", campaign=campaign, published=True, common_data=common)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_category', args=[campaign.import_id]), {'agree_license': 'on'}, follow=True,
        )

        naming_it = [text for text in self._message_texts(response) if "Marking Rubric" in text]
        self.assertEqual(len(naming_it), 1, f"expected exactly one message, got {self._message_texts(response)}")
        self.assertEqual(naming_it[0].count("Marking Rubric"), 1)

    def test_export_category__names_every_general_info_block_left_behind(self):
        """A campaign using two different General Info blocks names both of them.

        One message listing both, rather than one message each: they are the same kind of
        loss and the sharer fixes them the same way.
        """
        campaign = baker.make(Category, published=True)
        for title, quest_name in [("Marking Rubric", "Graded Quest"), ("Video Howto", "Filmed Quest")]:
            common = CommonData.objects.create(title=title, instructions=f"<p>{title}</p>")
            baker.make(Quest, name=quest_name, campaign=campaign, published=True, common_data=common)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_category', args=[campaign.import_id]), {'agree_license': 'on'}, follow=True,
        )

        naming_them = [
            text for text in self._message_texts(response)
            if "Marking Rubric" in text and "Video Howto" in text
        ]
        self.assertEqual(len(naming_them), 1, f"expected one message naming both, got {self._message_texts(response)}")

    def test_export_category__warns_the_sharer_that_an_archived_quest_was_left_out(self):
        """Sharing a campaign holding an archived quest names the quest that stayed behind.

        The push succeeds and the campaign looks complete, so the omission is invisible
        without this: it would surface on somebody else's deck, if at all (#2442).
        """
        campaign = baker.make(Category, published=True)
        active = baker.make(Quest, name="Still Active Quest", campaign=campaign, published=True)
        archived = baker.make(Quest, name="Retired Quest", campaign=campaign, published=True, archived=True)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_category', args=[campaign.import_id]), {'agree_license': 'on'}, follow=True,
        )

        texts = self._message_texts(response)
        self.assertTrue(
            any("Retired Quest" in text for text in texts),
            f"expected the archived quest to be named, got {texts}",
        )
        with library_schema_context():
            shared = set(Quest.objects.all_including_archived().values_list('import_id', flat=True))
        self.assertIn(active.import_id, shared)
        self.assertNotIn(archived.import_id, shared)

    def test_export_category__does_not_name_an_archived_quest_that_is_also_a_draft(self):
        """A draft is not reported as left behind, because unarchiving would not send it.

        The share carries `current_quests()`, which is published *and* not archived, so an
        archived draft fails both tests. Naming it would attach advice that does not work:
        unarchive it and share again, and it still would not travel. A draft not travelling
        is what a sharer expects anyway; an archived quest disappearing is not.
        """
        campaign = baker.make(Category, published=True)
        baker.make(Quest, name="Ordinary Shared Quest", campaign=campaign, published=True)
        baker.make(Quest, name="Archived Draft", campaign=campaign, published=False, archived=True)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_category', args=[campaign.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertFalse(
            any("Archived Draft" in text for text in self._message_texts(response)),
            f"an archived draft should not be reported, got {self._message_texts(response)}",
        )

    def test_export_category__stays_quiet_when_every_quest_travels(self):
        """A campaign with nothing archived shares without a left-behind warning."""
        campaign = baker.make(Category, published=True)
        baker.make(Quest, name="First Quest", campaign=campaign, published=True)
        baker.make(Quest, name="Second Quest", campaign=campaign, published=True)
        self._allow_staff_export()
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('library:export_category', args=[campaign.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertFalse(
            any("not included" in text for text in self._message_texts(response)),
            f"expected no warning, got {self._message_texts(response)}",
        )


class LibraryListingWindowTests(LibraryTenantTestCaseMixin):
    """The Library lists what it holds, not what the sharing deck's timetable allows.

    `date_available` and `date_expired` cross the schema boundary with the quest, so they
    describe the term of the deck that shared it. A catalogue that honoured those dates
    would drop a quest the day its original term ended, while leaving it importable
    through its campaign and by direct link, so the same quest would be missing from one
    tab and offered in the other.
    """

    @classmethod
    def setUpTestData(cls):
        """Add three published quests to the Library: ordinary, not yet available, expired.

        The Library tenant is seeded with quests of its own, so the counts below are
        measured against a baseline taken before these three are added.
        """
        with library_schema_context():
            cls.quests_already_in_library = Quest.objects.get_queryset().published().active_or_no_campaign().count()

            cls.library_campaign = baker.make(Category, published=True)
            cls.ordinary = baker.make(Quest, name="Ordinary Quest", campaign=cls.library_campaign, published=True)
            cls.not_yet = baker.make(
                Quest, name="Not Yet Available", campaign=cls.library_campaign, published=True,
                date_available=date(2099, 1, 1),
            )
            cls.expired = baker.make(
                Quest, name="Already Expired", campaign=cls.library_campaign, published=True,
                date_expired=date(2020, 1, 1),
            )

        cls.test_teacher = User.objects.create_user('listing_window_teacher', is_staff=True)

    def test_LibraryQuestListView__lists_a_quest_whose_availability_date_has_not_arrived(self):
        """A quest the sharing deck scheduled for a future date is still in the catalogue.

        Searched for by name rather than read off the first page: the list is paginated and
        unordered, so which page a quest lands on is not something the test should assume.
        """
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:quest_list'), {'q': 'Not Yet Available'})

        self.assertIn(self.not_yet, response.context['library_quests'])

    def test_LibraryQuestListView__lists_a_quest_whose_expiry_date_has_passed(self):
        """A quest that expired on the sharing deck is still in the catalogue."""
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:quest_list'), {'q': 'Already Expired'})

        self.assertIn(self.expired, response.context['library_quests'])

    def test_LibraryQuestListView__quest_badge_counts_every_quest_the_list_shows(self):
        """The Quests badge agrees with the list beneath it, all three new quests included."""
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:quest_list'))

        self.assertEqual(response.context['num_quests'], self.quests_already_in_library + 3)

    def test_LibraryCampaignListView__quest_badge_agrees_with_the_quests_tab(self):
        """The Quests badge shows the same total whichever tab the user is on."""
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:category_list'))

        self.assertEqual(response.context['num_quests'], self.quests_already_in_library + 3)

    def test_LibraryQuestListView__search_finds_a_quest_outside_the_sharing_deck_window(self):
        """Search reaches an expired quest, so it can be found rather than only imported by link."""
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('library:quest_list'), {'q': 'Already Expired'})

        self.assertIn(self.expired, response.context['library_quests'])
        self.assertEqual(response.context['num_matching_quests'], 1)


class LibraryImportPreviewQuestionTests(LibraryTenantTestCaseMixin):
    """What the import preview shows for a Library quest's submission questions (#2163).

    The page is rendered on the importing deck, so anything it reads lazily is read in that
    deck's schema. A quest's questions are exactly that, and a Library quest's id means a
    different quest here: the preview has to read them where they live, and must not offer
    to manage them from a page describing another schema's quest.
    """

    @classmethod
    def setUpTestData(cls):
        """Publish a Library quest that asks a question, and a teacher to preview it with."""
        with library_schema_context():
            cls.library_quest = baker.make(Quest, name="Library Quest With A Question", published=True)
            baker.make(
                Question, quest=cls.library_quest, ordinal=1,
                instructions="<p>What did the Library ask?</p>",
            )

        cls.test_teacher = User.objects.create_user('preview_teacher', is_staff=True)

    def preview(self):
        """Fetch the import preview page for the Library quest, as a teacher.

        Returns:
            HttpResponse: the rendered confirmation page.
        """
        self.client.force_login(self.test_teacher)
        return self.client.get(reverse('library:import_quest', args=[self.library_quest.import_id]))

    def _local_quest_sharing_the_library_quests_id(self):
        """Create a local quest holding the same primary key as the Library quest.

        That collision is what makes the bug visible rather than theoretical: primary keys
        are per schema, so the two ids mean different quests, and a preview reading the
        local table with the Library quest's id lands on this one.

        Returns:
            Quest: the local quest, with a question of its own.
        """
        local_quest = Quest(id=self.library_quest.id, name="A Totally Unrelated Local Quest", xp=5)
        local_quest.save(force_insert=True)
        # An explicit id leaves the table's sequence behind it, so the next quest created in
        # this schema would try to reuse an id that is now taken.
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence('quest_manager_quest', 'id'), (SELECT MAX(id) FROM quest_manager_quest))"
            )
        baker.make(Question, quest=local_quest, ordinal=1, instructions="<p>What does this deck ask?</p>")

        return local_quest

    def test_import_quest_get__shows_the_questions_the_library_quest_asks(self):
        """The preview lists the questions of the quest being imported."""
        response = self.preview()

        self.assertContains(response, "What did the Library ask?")

    def test_import_quest_get__does_not_show_another_decks_questions(self):
        """A local quest holding the same id does not get its questions shown instead (#2163).

        Whoever is deciding whether to import would otherwise be reading their own deck's
        questions, presented as the shared quest's.
        """
        self._local_quest_sharing_the_library_quests_id()

        response = self.preview()

        self.assertContains(response, "What did the Library ask?")
        self.assertNotContains(response, "What does this deck ask?")

    def test_import_quest_get__offers_no_way_to_edit_questions(self):
        """The preview drops the management buttons, which would address local rows.

        "Manage Questions", the reorder buttons and the edit and delete links are all keyed
        on the previewed quest's id, which belongs to another schema: followed from here
        they would act on whichever quest of this deck holds that id.
        """
        local_quest = self._local_quest_sharing_the_library_quests_id()
        local_question = Question.objects.get(quest=local_quest)

        response = self.preview()

        self.assertNotContains(response, reverse('questions:list', args=[self.library_quest.id]))
        self.assertNotContains(response, reverse('questions:move', args=[local_quest.id, local_question.id, 'up']))
        self.assertNotContains(response, local_question.get_absolute_url())
        self.assertNotContains(response, reverse('questions:delete', args=[local_quest.id, local_question.id]))

    def test_quest_detail__still_offers_question_management_on_the_deck_that_owns_the_quest(self):
        """The deck's own quest page keeps its buttons: there the ids mean what they say."""
        local_quest = baker.make(Quest, name="A Local Quest")
        baker.make(Question, quest=local_quest, ordinal=1, instructions="<p>Local question</p>")
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse('quests:quest_detail', args=[local_quest.id]))

        self.assertContains(response, reverse('questions:list', args=[local_quest.id]))


class LibraryLazyQuerysetRenderTests(LibraryTenantTestCaseMixin):
    """Related data on a Library page comes from the Library, not the viewer's own deck.

    Every Library view collects its objects inside `library_schema_context()`. Anything
    still lazy when the template renders is evaluated after the connection has switched
    back, so it queries this deck's tables using the Library row's primary key: no error,
    just another deck's data presented as the shared content's (#2369).

    Tags are the probe used throughout: they are a related manager on every listed quest,
    they render on all four pages, and taggit keys them by object id, so a local quest
    holding the same id supplies exactly the wrong answer.
    """

    @classmethod
    def setUpTestData(cls):
        """Publish a tagged quest with a prerequisite, and its campaign, in the Library, plus a staff viewer.

        The Library quest carries a tag and a prerequisite on a second Library quest, so a
        page can be checked for the Library's own values rather than only for the absence
        of this deck's.
        """
        with library_schema_context():
            cls.library_campaign = baker.make(Category, title="Chemistry Basics", published=True)
            cls.library_quest = baker.make(
                Quest, name="Titration Practice", campaign=cls.library_campaign, published=True,
            )
            cls.library_quest.tags.add("chemistry")
            # A prerequisite of the Library's own, so the pages can be checked for the
            # right one rather than only for the absence of the wrong one.
            cls.library_prereq = baker.make(Quest, name="Library Safety Briefing", published=True)
            Prereq.add_simple_prereq(cls.library_quest, cls.library_prereq)

        cls.test_teacher = User.objects.create_user('lazy_queryset_teacher', is_staff=True)

    def setUp(self):
        """Put decoys on this deck at the Library quest's id, and sign the teacher in.

        Both tags and prerequisites are keyed by the object id of the quest they belong to,
        so a local quest forced to the Library quest's id supplies exactly the wrong answer
        to anything evaluated after the schema switches back: a tag of `local-only` and a
        prerequisite on `Local Gate Quest`.
        """
        super().setUp()
        # taggit keys tags by object id, so a local quest at the Library quest's id is what
        # a lazily-evaluated `quest.tags.all` would find after the schema switches back.
        local = baker.make(Quest, name="A Local Quest")
        Quest.objects.filter(pk=local.pk).update(id=self.library_quest.id)
        decoy = Quest.objects.get(pk=self.library_quest.id)
        decoy.tags.add("local-only")
        # and a prerequisite of its own: prereqs are keyed by the parent's object id, so a
        # lazily-evaluated `quest.prereqs` finds this one once the schema switches back.
        Prereq.add_simple_prereq(decoy, baker.make(Quest, name="Local Gate Quest"))
        self.client.force_login(self.test_teacher)

    def assertShowsLibraryTags(self, response):
        """Assert a rendered page shows the Library quest's tag and not this deck's.

        Args:
            response (HttpResponse): the rendered Library page.

        Raises:
            AssertionError: if the page did not render, or shows this deck's tag in place
                of the Library's.
        """
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "chemistry")
        self.assertNotContains(response, "local-only")

    def test_LibraryQuestListView__shows_the_library_quests_own_tags(self):
        """The Library quest list renders tags read from the Library."""
        self.assertShowsLibraryTags(self.client.get(reverse('library:quest_list')))

    def test_CategoryDetailView__shows_the_library_quests_own_tags(self):
        """The Library campaign detail page renders tags read from the Library."""
        self.assertShowsLibraryTags(
            self.client.get(reverse('library:category_detail_view', args=[self.library_campaign.import_id]))
        )

    def test_ImportCampaignView__shows_the_library_quests_own_tags(self):
        """The campaign import preview renders tags read from the Library.

        This is the page a teacher decides on, so showing their own deck's data back to
        them is the most misleading place for it to happen.
        """
        self.assertShowsLibraryTags(
            self.client.get(reverse('library:import_category', args=[self.library_campaign.import_id]))
        )

    def test_ImportQuestView__shows_the_library_quests_own_tags(self):
        """The quest import preview renders tags read from the Library."""
        self.assertShowsLibraryTags(
            self.client.get(reverse('library:import_quest', args=[self.library_quest.import_id]))
        )

    def test_ImportQuestView__shows_the_library_quests_own_prereqs(self):
        """The quest import preview names the Library quest's prerequisite, not this deck's (#2529).

        The preview exists to say what is about to arrive, and this project has decided
        prerequisites are the importing deck's own business (#2375), so showing them one
        that is really their own, attached to a quest they do not have yet, is the most
        misleading thing the page could do.

        This is the only Library page that renders prerequisites server-side. The list and
        campaign pages show a quest's details through a later AJAX request, which renders
        inside its own schema context and so was never exposed to this.
        """
        response = self.client.get(reverse('library:import_quest', args=[self.library_quest.import_id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Library Safety Briefing")
        self.assertNotContains(response, "Local Gate Quest")


class LibraryImportCampaignPublishLinkTests(LibraryTenantTestCaseMixin):
    """The import message's publish link reaches the action it promises (#2533).

    The message tells the teacher that publishing the campaign publishes its quests. Only
    one control does that, and it is a POST-only button on the campaign's own page, so the
    link has to lead there: the campaign's edit form publishes the campaign alone and
    leaves every quest a draft, which looks identical to the teacher until a student says
    they cannot see anything.
    """

    @classmethod
    def setUpTestData(cls):
        """Create a staff user to import with."""
        cls.test_teacher = User.objects.create_user('publish_link_teacher', is_staff=True)

    def setUp(self):
        """Publish a one-quest campaign in the Library and sign the teacher in."""
        super().setUp()
        self.client.force_login(self.test_teacher)
        with library_schema_context():
            self.library_campaign = baker.make(Category, title="Digital Citizenship", published=True)
            baker.make(Quest, name="Your Digital Footprint", campaign=self.library_campaign, published=True)

    def _import_and_read_the_message(self):
        """Import the Library campaign and return the success message's HTML.

        Returns:
            str: the rendered message.
        """
        response = self.client.post(
            reverse('library:import_category', args=[self.library_campaign.import_id]), follow=True,
        )
        messages = [str(message) for message in response.context['messages']]
        return next(message for message in messages if "Successfully imported" in message)

    def test_import_campaign__the_publish_link_goes_to_the_campaign_page(self):
        """The "publish the campaign" link points at the campaign, not its edit form."""
        message = self._import_and_read_the_message()
        campaign = Category.objects.get(import_id=self.library_campaign.import_id)

        self.assertIn(f'<a href="{campaign.get_absolute_url()}">publish the campaign</a>', message)
        self.assertNotIn(reverse('quests:category_update', args=[campaign.id]), message)

    def test_import_campaign__the_page_the_publish_link_reaches_publishes_the_quests(self):
        """That page carries the control that publishes the campaign and its quests.

        Asserted by following the link rather than by naming a URL, so the test fails if
        the button moves or stops being offered, not merely if the link string changes.
        """
        self._import_and_read_the_message()
        campaign = Category.objects.get(import_id=self.library_campaign.import_id)

        response = self.client.get(campaign.get_absolute_url())

        self.assertContains(response, reverse('quests:category_publish', args=[campaign.id]))
        self.assertContains(response, "Publish Campaign and all its Quests")

    def test_category_publish__publishes_the_campaign_and_its_quests(self):
        """The linked-to control does publish both, which is what the message promises."""
        self._import_and_read_the_message()
        campaign = Category.objects.get(import_id=self.library_campaign.import_id)
        self.assertFalse(campaign.published)

        self.client.post(reverse('quests:category_publish', args=[campaign.id]))

        campaign.refresh_from_db()
        self.assertTrue(campaign.published)
        self.assertTrue(all(quest.published for quest in Quest.objects.filter(campaign=campaign)))


class LibraryImportCampaignPreviewTests(LibraryTenantTestCaseMixin):
    """What the campaign import confirmation page tells a teacher about the campaign.

    It is the page the import decision is made on, so the campaign's name, its blurb and
    the quests that would arrive all belong on it, and a campaign that genuinely has no
    blurb has to say so rather than leave a gap. The page reads some of that from the
    campaign object and some from values the view pre-computes, so these assert on what
    is rendered rather than on which source it came from (#2370).
    """

    @classmethod
    def setUpTestData(cls):
        """Publish a described campaign with one quest in the Library, and a staff user."""
        with library_schema_context():
            cls.library_campaign = baker.make(
                Category,
                title="Rendered Campaign Title",
                short_description="A blurb the importing teacher needs to read.",
                published=True,
            )
            cls.library_quest = baker.make(
                Quest, name="Previewed Quest", campaign=cls.library_campaign, published=True,
            )

        cls.test_teacher = User.objects.create_user('preview_teacher', is_staff=True)

    def preview(self):
        """Fetch the campaign import confirmation page as a signed-in teacher.

        Returns:
            HttpResponse: the rendered confirmation page.
        """
        self.client.force_login(self.test_teacher)

        return self.client.get(reverse('library:import_category', args=[self.library_campaign.import_id]))

    def test_ImportCampaignView__names_the_campaign_in_the_heading(self):
        """The heading says which campaign is being imported."""
        response = self.preview()

        self.assertContains(response, "Rendered Campaign Title")

    def test_ImportCampaignView__shows_the_campaigns_own_description(self):
        """The campaign's blurb is shown, rather than being reported as absent."""
        response = self.preview()

        self.assertContains(response, "A blurb the importing teacher needs to read.")
        self.assertNotContains(response, "[No description provided]")

    def test_ImportCampaignView__says_a_campaign_with_no_description_has_none(self):
        """A campaign that really has no blurb still says so, rather than showing nothing."""
        with library_schema_context():
            Category.objects.filter(pk=self.library_campaign.pk).update(short_description="")

        response = self.preview()

        self.assertContains(response, "[No description provided]")

    def test_ImportCampaignView__lists_the_campaigns_quests(self):
        """The quests that would arrive are listed, with their count and XP."""
        response = self.preview()

        self.assertContains(response, "Previewed Quest")
        self.assertContains(response, "Published quests in this campaign: 1")


class LibraryExportPermissionTests(LibraryTenantTestCaseMixin):
    """The export endpoints and the export buttons answer to one rule (#2368).

    `SiteConfig.can_user_export_to_library` decides whether the Share buttons render, and
    the export views' permission check decides whether the endpoints behind them run. Any
    difference between the two is a button that leads to a refusal, or worse, an endpoint
    that allows what no button offers.
    """

    @classmethod
    def setUpTestData(cls):
        """A deck owner and an ordinary teacher, the two sides of `allow_staff_export`."""
        cls.owner = User.objects.create_user('export_owner', is_staff=True)
        cls.teacher = User.objects.create_user('export_teacher', is_staff=True)

    def setUp(self):
        """Own the deck as `owner`, with staff sharing off and the Library enabled."""
        super().setUp()
        config = SiteConfig.get()
        config.deck_owner = self.owner
        config.allow_staff_export = False
        config.enable_shared_library = True
        config.save()

    def endpoint_allows(self, user):
        """Whether the export views would let this user through, on the current schema.

        Args:
            user (User): the user making the request.

        Returns:
            bool: True when the permission check passes, False when it raises.
        """
        request = RequestFactory().post('/')
        request.user = user

        try:
            ExportQuestView()._require_export_permission(request)
        except PermissionDenied:
            return False

        return True

    def button_offers(self, user):
        """Whether the Share buttons would be offered to this user, on the current schema.

        Args:
            user (User): the user viewing the page.

        Returns:
            bool: what the button gate decides.
        """
        return SiteConfig.get().can_user_export_to_library(user)

    def assertEndpointAgreesWithButton(self, user):
        """Assert the endpoint and the button reach the same verdict for a user.

        Args:
            user (User): the user to check both gates for.

        Raises:
            AssertionError: if one gate would allow what the other refuses.
        """
        offered = self.button_offers(user)
        self.assertEqual(
            self.endpoint_allows(user),
            offered,
            f"the endpoint and the button disagree for {user}: button offers={offered}",
        )

    def test_ExportPermissionMixin__refuses_an_export_from_the_library_deck(self):
        """The Library does not share into itself, whoever asks.

        Content reaching the Library is a copy from somewhere else, so an export run from
        the Library deck has no meaning: it would be copying a quest over itself.

        The Library deck's own config is opened up first, so being on the Library schema is
        the only thing left that can refuse. Without that the check would pass on the
        Library deck simply not recognising this user, which is true of every user and would
        hide whether the schema rule is applied at all.

        Its `deck_owner` is left alone: users are per-schema, so the Library's config cannot
        point at a user from this deck. Staff sharing covers the same ground here, since the
        user is staff.
        """
        with library_schema_context():
            library_config = SiteConfig.get()
            library_config.allow_staff_export = True
            library_config.enable_shared_library = True
            library_config.save()

            self.assertFalse(self.endpoint_allows(self.owner))
            self.assertEndpointAgreesWithButton(self.owner)

    def test_ExportPermissionMixin__lets_the_deck_owner_export(self):
        """The deck owner can always share from their own deck."""
        self.assertTrue(self.endpoint_allows(self.owner))
        self.assertEndpointAgreesWithButton(self.owner)

    def test_ExportPermissionMixin__refuses_other_staff_while_staff_sharing_is_off(self):
        """With `allow_staff_export` off, sharing is the deck owner's decision alone."""
        self.assertFalse(self.endpoint_allows(self.teacher))
        self.assertEndpointAgreesWithButton(self.teacher)

    def test_ExportPermissionMixin__lets_other_staff_export_once_staff_sharing_is_on(self):
        """With `allow_staff_export` on, any teacher on the deck can share."""
        config = SiteConfig.get()
        config.allow_staff_export = True
        config.save()

        self.assertTrue(self.endpoint_allows(self.teacher))
        self.assertEndpointAgreesWithButton(self.teacher)

    def test_ExportPermissionMixin__refuses_everyone_when_the_shared_library_is_off(self):
        """A deck that opted out of the Library cannot share to it.

        The view decorator 404s such a request first, so this is the second line rather
        than the one users meet; it matters because it is what keeps the two gates equal.
        """
        config = SiteConfig.get()
        config.enable_shared_library = False
        config.save()

        self.assertFalse(self.endpoint_allows(self.owner))
        self.assertEndpointAgreesWithButton(self.owner)


class LibraryConflictMessageTests(LibraryTenantTestCaseMixin):
    """Content that is already on the other side is a conflict, not a permission problem.

    The confirmation pages disable the button in these cases, so the guards behind them
    only fire when the button was not what was clicked: a stale tab, the back button, a
    resubmitted form, or two teachers working at once. Meeting a bare 403 there says the
    user did something forbidden, when what happened is that somebody got there first
    (#2373).
    """

    @classmethod
    def setUpTestData(cls):
        """Publish a quest and a campaign in the Library, and a staff user to move them."""
        with library_schema_context():
            cls.library_campaign = baker.make(Category, title="Contested Campaign", published=True)
            cls.library_quest = baker.make(
                Quest, name="Contested Quest", campaign=cls.library_campaign, published=True,
            )

        cls.test_teacher = User.objects.create_user('conflict_teacher', is_staff=True)

    def setUp(self):
        """Sign the teacher in and let them share, so only the conflict guards can refuse."""
        super().setUp()
        config = SiteConfig.get()
        config.allow_staff_export = True
        config.save()
        self.client.force_login(self.test_teacher)

    def local_copy_of(self, model, obj, **kwargs):
        """Give this deck its own copy of a Library object, under the same import_id.

        Args:
            model (type[Model]): Quest or Category.
            obj (Model): the Library object to mirror.
            **kwargs: extra field values for the local copy.

        Returns:
            Model: the local copy.
        """
        return baker.make(model, import_id=obj.import_id, **kwargs)

    def test_ImportQuestView__explains_that_the_deck_already_has_the_quest(self):
        """Re-importing a quest this deck already holds explains itself instead of 403ing."""
        local = self.local_copy_of(Quest, self.library_quest, name="Our Own Copy")

        response = self.client.post(
            reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any("Our Own Copy" in text for text in self._message_texts(response)),
            f"expected the local quest to be named, got {self._message_texts(response)}",
        )
        self.assertContains(response, local.get_absolute_url())

    def test_ImportCampaignView__explains_that_the_deck_already_has_the_campaign(self):
        """Re-importing a campaign this deck already holds explains itself instead of 403ing."""
        local = self.local_copy_of(Category, self.library_campaign, title="Our Own Campaign")

        response = self.client.post(
            reverse('library:import_category', args=[self.library_campaign.import_id]), follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any("Our Own Campaign" in text for text in self._message_texts(response)),
            f"expected the local campaign to be named, got {self._message_texts(response)}",
        )
        self.assertContains(response, local.get_absolute_url())

    def test_ExportQuestView__explains_that_the_quest_is_already_in_the_library(self):
        """Re-sharing a quest already in the Library explains itself instead of 403ing."""
        local = self.local_copy_of(Quest, self.library_quest, name="Already Shared Quest")

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any("Already Shared Quest" in text for text in self._message_texts(response)),
            f"expected the quest to be named, got {self._message_texts(response)}",
        )

    def test_ExportCampaignView__explains_that_the_campaign_is_already_in_the_library(self):
        """Re-sharing a campaign already in the Library explains itself instead of 403ing."""
        local = self.local_copy_of(Category, self.library_campaign, title="Already Shared Campaign")
        baker.make(Quest, campaign=local, published=True)

        response = self.client.post(
            reverse('library:export_category', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            any("Already Shared Campaign" in text for text in self._message_texts(response)),
            f"expected the campaign to be named, got {self._message_texts(response)}",
        )

    def test_ImportQuestView__adds_nothing_when_the_deck_already_has_the_quest(self):
        """The guard still holds: explaining the conflict must not also perform the import."""
        self.local_copy_of(Quest, self.library_quest, name="Our Own Copy")

        self.client.post(reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True)

        self.assertEqual(
            Quest.objects.all_including_archived().filter(import_id=self.library_quest.import_id).count(), 1,
        )

    def test_ImportQuestView__escapes_markup_in_a_quest_name(self):
        """A quest name carrying markup reaches the page as text, not as markup.

        Every message renders through `|safe` (`templates/messages-snippet.html`), so a
        name interpolated into one goes to the browser as HTML. Quest names are written by
        staff, which narrows who could do it, not what happens if they do.
        """
        self.local_copy_of(Quest, self.library_quest, name="<script>alert(1)</script>")

        response = self.client.post(
            reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True,
        )

        self.assertNotContains(response, "<script>alert(1)</script>", html=False)
        self.assertContains(response, "&lt;script&gt;alert(1)&lt;/script&gt;")

    def test_ExportQuestView__escapes_markup_in_a_quest_name(self):
        """The share-side message escapes a name carrying markup too."""
        local = self.local_copy_of(Quest, self.library_quest, name="<script>alert(2)</script>")

        response = self.client.post(
            reverse('library:export_quest', args=[local.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertNotContains(response, "<script>alert(2)</script>", html=False)
        self.assertContains(response, "&lt;script&gt;alert(2)&lt;/script&gt;")

    def test_ImportQuestView__keeps_the_link_to_the_local_copy_live(self):
        """Escaping the name must not also escape the link the message provides."""
        local = self.local_copy_of(Quest, self.library_quest, name="Our Own Copy")

        response = self.client.post(
            reverse('library:import_quest', args=[self.library_quest.import_id]), follow=True,
        )

        self.assertContains(response, f'<a href="{local.get_absolute_url()}">Our Own Copy</a>')


class LibraryPushAtomicityTests(LibraryTenantTestCaseMixin):
    """A push either lands whole or leaves the Library as it was (#2372).

    A campaign push writes in several steps: its own quests, the campaign row, and the
    conflict clones. Between them the Library holds part of a campaign, and a failure
    there would strand it: quests whose prerequisites point at ones that never arrived,
    under a campaign nobody pushed on purpose, with the sharer told nothing happened.
    """

    @classmethod
    def setUpTestData(cls):
        """A staff user here, and a Library reviewer with an address to email."""
        cls.test_teacher = User.objects.create_user('atomic_teacher', is_staff=True)
        with library_schema_context():
            # The review email goes to Library staff with an address, and returns early
            # without one, which would make the "no email on failure" test vacuous.
            User.objects.create_user('library_reviewer', email='reviewer@example.com', is_staff=True)

    def setUp(self):
        """Let staff share, sign the teacher in, and build the campaign to push."""
        super().setUp()
        config = SiteConfig.get()
        config.allow_staff_export = True
        config.save()
        self.client.force_login(self.test_teacher)

        self.campaign = baker.make(Category, title="Atomic Campaign", published=True)
        for name in ["Atomic Quest One", "Atomic Quest Two"]:
            quest = baker.make(Quest, name=name, campaign=self.campaign)
            Quest.objects.filter(pk=quest.pk).update(published=True)

    def library_holds_anything(self):
        """Whether the Library holds any part of the campaign being pushed.

        Returns:
            bool: True if its campaign row or either of its quests is there.
        """
        with library_schema_context():
            return (
                Category.objects.filter(import_id=self.campaign.import_id).exists()
                or Quest.objects.all_including_archived().filter(name__startswith="Atomic Quest").exists()
            )

    def test_ExportCampaignView__leaves_the_library_untouched_when_the_push_fails(self):
        """A failure part-way through a campaign push rolls the whole push back.

        The origin row is written after the content, in the same transaction, so failing
        there is the narrow case that used to leave the content behind with nothing to
        undo it.
        """
        with patch('library.views.record_push_origin', side_effect=IntegrityError("no origin for you")):
            with self.assertRaises(IntegrityError):
                self.client.post(
                    reverse('library:export_category', args=[self.campaign.import_id]), {'agree_license': 'on'},
                )

        self.assertFalse(self.library_holds_anything())

    def test_ExportCampaignView__sends_no_review_email_when_the_push_fails(self):
        """Nobody is invited to review content that was rolled back.

        An email cannot be recalled, so it waits for the transaction to commit rather
        than going out as soon as the code reaches it.
        """
        with patch('library.views.send_email_message') as send_email:
            with patch('library.views.record_push_origin', side_effect=IntegrityError("no origin for you")):
                with self.assertRaises(IntegrityError):
                    self.client.post(
                        reverse('library:export_category', args=[self.campaign.import_id]), {'agree_license': 'on'},
                    )

        send_email.apply_async.assert_not_called()

    def test_ExportCampaignView__sends_the_review_email_when_the_push_succeeds(self):
        """The deferral must not swallow the email on the path that should send one.

        Pairs with the test above: on its own, "no email on failure" would also pass if the
        email had simply stopped being sent.
        """
        # The patch has to outlive the capture block: the callbacks run when the capture
        # block exits, which is after an inner patch would have been undone.
        with patch('library.views.send_email_message') as send_email:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(
                    reverse('library:export_category', args=[self.campaign.import_id]), {'agree_license': 'on'},
                )

        send_email.apply_async.assert_called_once()

    def test_ExportCampaignView__pushes_the_whole_campaign_when_nothing_fails(self):
        """The transaction is not so tight that an ordinary push stops working."""
        response = self.client.post(
            reverse('library:export_category', args=[self.campaign.import_id]), {'agree_license': 'on'}, follow=True,
        )

        self.assertEqual(response.status_code, 200)
        with library_schema_context():
            self.assertTrue(Category.objects.filter(import_id=self.campaign.import_id).exists())
            self.assertEqual(Quest.objects.all_including_archived().filter(name__startswith="Atomic Quest").count(), 2)
