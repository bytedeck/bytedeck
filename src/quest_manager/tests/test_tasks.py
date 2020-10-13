from django.contrib.auth import get_user_model

from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase

from quest_manager import tasks
from quest_manager.models import Quest, QuestSubmission

User = get_user_model()


class QuestTasksTests(TenantTestCase):

    def setUp(self):
        self.quest = baker.make(Quest, visible_to_students=True)
        self.student1 = baker.make(User)
        self.student2 = baker.make(User)

    def test_remove_quest_submissions_for_hidden_quest(self):
        # Create 2 submissions for a quest
        baker.make(QuestSubmission, user=self.student1, quest=self.quest)
        baker.make(QuestSubmission, user=self.student2, quest=self.quest)

        # There should be 2 submissions
        self.assertEqual(QuestSubmission.objects.count(), 2)

        task_result = tasks.remove_quest_submissions_for_hidden_quest.apply(
            kwargs={
                "quest_id": self.quest.id
            }
        )

        self.assertTrue(task_result.successful())
        # and after running the task, there should be 0.
        self.assertEqual(QuestSubmission.objects.count(), 0)
