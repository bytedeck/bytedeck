from django.test import SimpleTestCase

from quest_manager.templatetags.quest_tags import can_export_to_library, is_hidden


class QuestTagsIsHiddenTest(SimpleTestCase):
    """Tests for the is_hidden template filter's None-argument guard."""

    def test_is_hidden__returns_none_when_user_missing(self):
        """With no user, is_hidden short-circuits to None without touching the profile."""
        self.assertIsNone(is_hidden(object(), None))

    def test_is_hidden__returns_none_when_quest_missing(self):
        """With no quest, is_hidden short-circuits to None without touching the profile."""
        self.assertIsNone(is_hidden(None, object()))


class QuestTagsCanExportToLibraryTest(SimpleTestCase):
    """Tests for the can_export_to_library tag's missing-request guard.

    The tag's real answer (per user, per SiteConfig, per schema) is exercised through
    full page renders in the view tests; only the guard needs a direct call.
    """

    def test_can_export_to_library__returns_false_without_request(self):
        """Rendered without a RequestContext there is no user to allow, so no export button."""
        self.assertFalse(can_export_to_library({}))
