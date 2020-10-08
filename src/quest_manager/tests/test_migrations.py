from django_tenants.test.cases import TenantTestCase

from quest_manager.models import Quest


class QuestMigrationTest(TenantTestCase):
    """ Tests of the data migrations that install initial quest data
    """

    def test_default_quests_created(self):
        """ A data migration should make 6 initial quests """
        self.assertEqual(Quest.objects.count(), 6)
