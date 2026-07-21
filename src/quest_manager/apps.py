from django.apps import AppConfig


class QuestConfig(AppConfig):
    name = 'quest_manager'
    verbose_name = 'Quests'

    def ready(self):
        # noinspection PyUnresolvedReferences
        import quest_manager.signals # noqa
