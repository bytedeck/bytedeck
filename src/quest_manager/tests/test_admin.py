from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.admin import (
    archive_selected_quests,
    fix_whitespace_bug,
    prettify_code_selected_quests,
    publish_selected_quests,
)
from quest_manager.models import Quest

User = get_user_model()


def _request_with_messages():
    request = RequestFactory().get('/')
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class QuestAdminActionsTest(ByteDeckTenantTestCase):
    """Tests for the module-level admin actions registered on QuestAdmin."""

    def test_publish_selected_quests(self):
        """Publishing sets published=True and clears the editor on each selected quest."""
        editor = baker.make(User)
        quest = baker.make(Quest, published=False, editor=editor)
        request = _request_with_messages()

        publish_selected_quests(None, request, Quest.objects.filter(pk=quest.pk))

        quest.refresh_from_db()
        self.assertTrue(quest.published)
        self.assertIsNone(quest.editor)
        self.assertEqual(len(list(request._messages)), 1)

    def test_archive_selected_quests(self):
        """Archiving sets archived=True, published=False and clears the editor."""
        quest = baker.make(Quest, archived=False, published=True)
        request = _request_with_messages()

        archive_selected_quests(None, request, Quest.objects.filter(pk=quest.pk))

        quest.refresh_from_db()
        self.assertTrue(quest.archived)
        self.assertFalse(quest.published)
        self.assertEqual(len(list(request._messages)), 1)

    def test_prettify_code_selected_quests(self):
        """Prettifying rewrites the instructions HTML in place and reports success."""
        quest = baker.make(Quest, instructions='<div><p>hi</p></div>')
        request = _request_with_messages()

        prettify_code_selected_quests(None, request, Quest.objects.filter(pk=quest.pk))

        quest.refresh_from_db()
        # tidy_html indents block tags onto their own lines.
        self.assertIn('\n', quest.instructions)
        self.assertEqual(len(list(request._messages)), 1)

    def test_fix_whitespace_bug(self):
        """The whitespace-bug fixer also rewrites instructions and reports success."""
        quest = baker.make(Quest, instructions='<div><p>hi</p></div>')
        request = _request_with_messages()

        fix_whitespace_bug(None, request, Quest.objects.filter(pk=quest.pk))

        quest.refresh_from_db()
        self.assertIn('\n', quest.instructions)
        self.assertEqual(len(list(request._messages)), 1)
