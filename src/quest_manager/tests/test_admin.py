import uuid

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model

from model_bakery import baker

from badges.models import Badge
from hackerspace_online.tests.utils import ByteDeckTenantTestCase, request_with_messages
from prerequisites.models import Prereq
from quest_manager.admin import (
    QuestAdmin,
    QuestAdminExportResource,
    QuestResource,
    QuestSubmissionAdmin,
    archive_selected_quests,
    fix_whitespace_bug,
    prettify_code_selected_quests,
    publish_selected_quests,
)
from quest_manager.models import Category, Quest, QuestSubmission

User = get_user_model()


class QuestAdminActionsTest(ByteDeckTenantTestCase):
    """Tests for the module-level admin actions registered on QuestAdmin."""

    def test_publish_selected_quests__publishes_and_clears_editor(self):
        """Publishing sets published=True and clears the editor on each selected quest."""
        editor = baker.make(User)
        quest = baker.make(Quest, published=False, editor=editor)
        request = request_with_messages()

        publish_selected_quests(None, request, Quest.objects.filter(pk=quest.pk))

        quest.refresh_from_db()
        self.assertTrue(quest.published)
        self.assertIsNone(quest.editor)
        self.assertEqual(len(list(request._messages)), 1)

    def test_archive_selected_quests__archives_and_unpublishes(self):
        """Archiving sets archived=True, published=False and clears the editor."""
        quest = baker.make(Quest, archived=False, published=True)
        request = request_with_messages()

        archive_selected_quests(None, request, Quest.objects.filter(pk=quest.pk))

        quest.refresh_from_db()
        self.assertTrue(quest.archived)
        self.assertFalse(quest.published)
        self.assertEqual(len(list(request._messages)), 1)

    def test_prettify_code_selected_quests__rewrites_instructions(self):
        """Prettifying rewrites the instructions HTML in place and reports success."""
        quest = baker.make(Quest, instructions='<div><p>hi</p></div>')
        request = request_with_messages()

        prettify_code_selected_quests(None, request, Quest.objects.filter(pk=quest.pk))

        quest.refresh_from_db()
        # tidy_html indents block tags onto their own lines.
        self.assertIn('\n', quest.instructions)
        self.assertEqual(len(list(request._messages)), 1)

    def test_fix_whitespace_bug__rewrites_instructions(self):
        """The whitespace-bug fixer also rewrites instructions and reports success."""
        quest = baker.make(Quest, instructions='<div><p>hi</p></div>')
        request = request_with_messages()

        fix_whitespace_bug(None, request, Quest.objects.filter(pk=quest.pk))

        quest.refresh_from_db()
        self.assertIn('\n', quest.instructions)
        self.assertEqual(len(list(request._messages)), 1)


class QuestSubmissionAdminQuerysetTest(ByteDeckTenantTestCase):
    """Tests for QuestSubmissionAdmin.get_queryset, which deliberately returns rows the
    default manager hides (other semesters, archived quests, unpublished quests)."""

    def test_get_queryset__returns_submissions_for_archived_and_unpublished_quests(self):
        """The admin queryset includes submissions the default manager excludes."""
        modeladmin = QuestSubmissionAdmin(QuestSubmission, django_admin.site)
        request = request_with_messages()
        # A submission on an archived + unpublished quest is hidden by the default manager.
        quest = baker.make(Quest, archived=True, published=False)
        submission = baker.make(QuestSubmission, quest=quest)

        self.assertIn(submission, modeladmin.get_queryset(request))

    def test_get_queryset__applies_admin_ordering_when_set(self):
        """When the admin defines an ordering, get_queryset applies it (order_by branch)."""
        modeladmin = QuestSubmissionAdmin(QuestSubmission, django_admin.site)
        modeladmin.ordering = ('-id',)
        request = request_with_messages()
        first = baker.make(QuestSubmission)
        second = baker.make(QuestSubmission)

        ordered = list(modeladmin.get_queryset(request))
        # '-id' ordering puts the later-created (higher pk) submission ahead of the earlier one.
        self.assertLess(ordered.index(second), ordered.index(first))


class QuestAdminQuerysetAndFormatsTest(ByteDeckTenantTestCase):
    """Tests for QuestAdmin.get_queryset (includes archived) and the import/export format lists."""

    def test_get_queryset__includes_archived_quests(self):
        """QuestAdmin.get_queryset includes archived quests, which the default manager hides."""
        modeladmin = QuestAdmin(Quest, django_admin.site)
        request = request_with_messages()
        archived = baker.make(Quest, archived=True)

        self.assertIn(archived, modeladmin.get_queryset(request))

    def test_get_import_formats__csv_only(self):
        """Importing is restricted to CSV."""
        modeladmin = QuestAdmin(Quest, django_admin.site)
        formats = modeladmin.get_import_formats()
        self.assertEqual([fmt().get_title() for fmt in formats], ['csv'])

    def test_get_export_formats__csv_only(self):
        """Exporting is restricted to CSV."""
        modeladmin = QuestAdmin(Quest, django_admin.site)
        formats = modeladmin.get_export_formats()
        self.assertEqual([fmt().get_title() for fmt in formats], ['csv'])


class QuestAdminExportResourceTest(ByteDeckTenantTestCase):
    """The admin Export button drops bulky summernote HTML columns to bound per-request
    memory (#2081), while the full QuestResource used by import / the Shared Library keeps
    them so cross-deck sharing is unaffected."""

    def test_admin_export_resource__omits_bulky_html_columns(self):
        """QuestAdminExportResource's export has no instructions/submission_details/instructor_notes columns."""
        quest = baker.make(Quest, instructions='<p>lots of html</p>', submission_details='<p>details</p>')

        headers = QuestAdminExportResource().export([quest]).headers

        # Assert each bulky column explicitly (not by iterating the constant) so an
        # incorrect or incomplete QUEST_EXPORT_EXCLUDED_HTML_FIELDS is caught here too.
        self.assertNotIn('instructions', headers)
        self.assertNotIn('submission_details', headers)
        self.assertNotIn('instructor_notes', headers)
        # Identifying/lightweight columns are still exported.
        self.assertIn('name', headers)

    def test_full_resource__still_exports_html_columns(self):
        """The full QuestResource (import + Shared Library) still carries every bulky HTML field."""
        quest = baker.make(Quest, instructions='<p>keep me</p>')

        dataset = QuestResource().export([quest])

        self.assertIn('instructions', dataset.headers)
        self.assertIn('submission_details', dataset.headers)
        self.assertIn('instructor_notes', dataset.headers)

    def test_quest_admin__export_uses_slim_resource_import_uses_full(self):
        """QuestAdmin exports with the slim resource but imports with the full one."""
        modeladmin = QuestAdmin(Quest, django_admin.site)
        request = request_with_messages()

        self.assertEqual(modeladmin.get_export_resource_classes(request), [QuestAdminExportResource])
        self.assertEqual(modeladmin.get_import_resource_classes(request), [QuestResource])


class QuestResourceDehydratePrereqsTest(ByteDeckTenantTestCase):
    """Tests for QuestResource.dehydrate_prereq_import_ids, used when exporting quests."""

    def test_dehydrate_prereq_import_ids__lists_quest_and_badge_prereqs(self):
        """Simple quest/badge prereqs are exported as an '&'-separated list of import_ids."""
        quest = baker.make(Quest)
        prereq_quest = baker.make(Quest)
        prereq_badge = baker.make(Badge)
        Prereq.add_simple_prereq(quest, prereq_quest)
        Prereq.add_simple_prereq(quest, prereq_badge)

        result = QuestResource().dehydrate_prereq_import_ids(quest)

        self.assertIn(str(prereq_quest.import_id), result)
        self.assertIn(str(prereq_badge.import_id), result)

    def test_dehydrate_prereq_import_ids__empty_when_no_prereqs(self):
        """A quest with no prereqs exports an empty string."""
        quest = baker.make(Quest)
        self.assertEqual(QuestResource().dehydrate_prereq_import_ids(quest), '')

    def test_dehydrate_prereq_import_ids__skips_non_quest_or_badge_prereqs(self):
        """Prereqs that aren't quests or badges (e.g. a campaign) are not exportable and are skipped."""
        quest = baker.make(Quest)
        campaign = baker.make(Category)
        Prereq.add_simple_prereq(quest, campaign)

        self.assertEqual(QuestResource().dehydrate_prereq_import_ids(quest), '')


class QuestResourceGenerateSimplePrereqsTest(ByteDeckTenantTestCase):
    """Tests for QuestResource.generate_simple_prereqs, which rebuilds prereqs on import."""

    def test_generate_simple_prereqs__links_existing_quest_prereq(self):
        """An import_id matching a local quest is added as a simple prereq of the parent."""
        parent = baker.make(Quest)
        prereq_quest = baker.make(Quest)
        data_dict = {'prereq_import_ids': '&' + str(prereq_quest.import_id)}

        QuestResource().generate_simple_prereqs(parent, data_dict)

        self.assertIn(prereq_quest, [p.get_prereq() for p in parent.prereqs()])

    def test_generate_simple_prereqs__links_existing_badge_prereq(self):
        """When no quest matches the import_id, a matching badge is used instead."""
        parent = baker.make(Quest)
        prereq_badge = baker.make(Badge)
        data_dict = {'prereq_import_ids': '&' + str(prereq_badge.import_id)}

        QuestResource().generate_simple_prereqs(parent, data_dict)

        self.assertIn(prereq_badge, [p.get_prereq() for p in parent.prereqs()])

    def test_generate_simple_prereqs__does_not_duplicate_existing_prereq(self):
        """Re-importing an already-linked prereq does not add a second one."""
        parent = baker.make(Quest)
        prereq_quest = baker.make(Quest)
        Prereq.add_simple_prereq(parent, prereq_quest)
        data_dict = {'prereq_import_ids': '&' + str(prereq_quest.import_id)}

        QuestResource().generate_simple_prereqs(parent, data_dict)

        prereqs = [p.get_prereq() for p in parent.prereqs()]
        self.assertEqual(prereqs.count(prereq_quest), 1)

    def test_generate_simple_prereqs__unknown_import_id_adds_nothing(self):
        """An import_id matching neither a quest nor a badge is silently skipped."""
        parent = baker.make(Quest)
        data_dict = {'prereq_import_ids': '&' + str(uuid.uuid4())}

        QuestResource().generate_simple_prereqs(parent, data_dict)

        self.assertEqual(parent.prereqs().count(), 0)


class QuestResourceGenerateCampaignTest(ByteDeckTenantTestCase):
    """Tests for QuestResource.generate_campaign, which assigns/creates a campaign on import."""

    def _resource(self):
        """A QuestResource with an empty visibility map (set on a real import by after_import)."""
        resource = QuestResource()
        resource.local_visibility_map = {}
        return resource

    def test_generate_campaign__no_import_id_falls_back_to_existing_title(self):
        """With no campaign_import_id, the campaign is matched by title instead (import_id lookup
        is skipped)."""
        existing = baker.make(Category, title='Existing Campaign')
        quest = baker.make(Quest)
        data_dict = {
            'campaign_title': 'Existing Campaign',
            'campaign_icon': None,
            'campaign_short_description': '',
            'campaign_import_id': None,
        }

        self._resource().generate_campaign(quest, data_dict)

        quest.refresh_from_db()
        self.assertEqual(quest.campaign, existing)


class QuestResourceAfterImportTest(ByteDeckTenantTestCase):
    """Tests for QuestResource.after_import, the post-import hook."""

    def test_after_import__is_a_noop_during_dry_run(self):
        """On a dry run (the import confirmation step) after_import returns without processing,
        so it never stores the visibility map."""
        resource = QuestResource()
        resource.local_visibility_map = 'SENTINEL'

        resource.after_import(dataset=None, result=None, dry_run=True)

        # the dry-run guard skips the body that would overwrite the visibility map
        self.assertEqual(resource.local_visibility_map, 'SENTINEL')
