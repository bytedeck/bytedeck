import uuid

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model

from model_bakery import baker

from badges.models import Badge
from hackerspace_online.tests.utils import ByteDeckTenantTestCase, request_with_messages
from prerequisites.models import Prereq
from quest_manager.admin import (
    QuestAdmin,
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
