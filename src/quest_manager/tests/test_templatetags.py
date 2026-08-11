from django.test import SimpleTestCase

from quest_manager.templatetags.quest_tags import is_hidden


class QuestTagsIsHiddenTest(SimpleTestCase):
    """Tests for the is_hidden template filter's None-argument guard."""

    def test_is_hidden__returns_none_when_user_missing(self):
        """With no user, is_hidden short-circuits to None without touching the profile."""
        self.assertIsNone(is_hidden(object(), None))

    def test_is_hidden__returns_none_when_quest_missing(self):
        """With no quest, is_hidden short-circuits to None without touching the profile."""
        self.assertIsNone(is_hidden(None, object()))
