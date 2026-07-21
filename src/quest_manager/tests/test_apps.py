from django.apps import apps
from django.test import SimpleTestCase

from quest_manager.apps import QuestConfig


class QuestManagerAppConfigTest(SimpleTestCase):
    """Guards that quest_manager loads its own AppConfig so QuestConfig.ready() runs."""

    def test_app_config__is_quest_config(self):
        """quest_manager resolves to QuestConfig (in apps.py), not Django's base AppConfig.

        QuestConfig.ready() is what imports quest_manager.signals and connects the
        pre_save/pre_delete receivers. Django 5.2 dropped the old ``default_app_config``
        hook, so the config must live in ``apps.py`` to be autodiscovered. Previously it
        lived in ``app.py`` referenced only via ``default_app_config``, so under Django 5.2
        ready() silently never ran (the app fell back to the base AppConfig) -- this test
        guards against that regression.
        """
        self.assertIsInstance(apps.get_app_config("quest_manager"), QuestConfig)
