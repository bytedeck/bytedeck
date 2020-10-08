from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from freezegun import freeze_time
from mock import patch
from model_bakery import baker

from badges.models import Badge, BadgeAssertion
from courses.models import CourseStudent, Semester
from prerequisites.models import Prereq
from quest_manager.models import Quest, QuestSubmission

User = get_user_model()


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class PrerequisitesSignalsTest(TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.teacher = baker.make(User, username='teacher', is_staff=True)
        self.student = baker.make(User, username='student', is_staff=False)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_badge_assertion(self, task):
        """Creation of a new badge assertion (granting a badge to a student) should...
        Updating of a badge assertion should...
        """
        sem = baker.make(Semester)  # not sure why model baker doesn't create this automatically
        badge_assertion = baker.make(BadgeAssertion, user=self.student, do_not_grant_xp=True, semester=sem)
        badge_assertion.do_not_grant_xp = False
        badge_assertion.save()
        self.assertEqual(task.call_count, 2)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_quest_summission(self, task):
        """Creation of a new quest_submission should...
        Updating of a quest_submission should...
        """
        quest_summission = baker.make(QuestSubmission, user=self.student, is_completed=False)
        quest_summission.is_completed = True
        quest_summission.save()
        self.assertEqual(task.call_count, 2)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_course_student(self, task):
        with patch('profile_manager.models.Profile.xp_invalidate_cache') as callback:
            course_student = baker.make(CourseStudent, user=self.student, active=False)
            course_student.active = True
            course_student.save()
            self.assertEqual(task.call_count, 2)
            self.assertEqual(callback.call_count, 2)

    @patch('prerequisites.signals.update_quest_conditions_all_users.apply_async')
    def test_update_prereq_cache_triggered_by_badge(self, task):
        """Creation and Update of a badge should...
        """
        badge = baker.make(Badge, active=True)  # creation
        badge.active = False
        badge.save()  # update
        self.assertEqual(task.call_count, 2)

    @patch('prerequisites.signals.update_conditions_for_quest.apply_async')
    def test_update_prereq_cache_triggered_by_quest(self, task):
        """Creation and Update of a quest should not trigger a cache update, only when a prereq is added to the quest (covered elsewhere).
        """
        quest = baker.make(Quest, verification_required=True)  # creation
        quest.verification_required = False
        quest.save()  # update
        self.assertEqual(task.call_count, 0)

    @patch('prerequisites.signals.update_conditions_for_quest.apply_async')
    def test_update_cache_triggered_by_non_quest_prereq(self, task):
        """Creation and Update of a prereq where the parent is not a quest should not trigger a cache update
        """
        badge = baker.make(Badge)
        prereq = baker.make(Prereq, prereq_invert=True, parent_object=badge)  # creation
        prereq.prereq_invert = False
        prereq.save()  # update
        self.assertEqual(task.call_count, 0)

    @patch('prerequisites.signals.update_conditions_for_quest.apply_async')
    def test_update_cache_triggered_by_quest_prereq_changes(self, task):
        """Creation and Update of a prereq where the parent IS a quest should both trigger a cache update
        """
        quest = baker.make('quest_manager.quest')
        prereq = baker.make(Prereq, prereq_invert=True, parent_object=quest)  # creation
        prereq.prereq_invert = False
        prereq.save()  # update
        self.assertEqual(task.call_count, 2)
        task.assert_called_with(kwargs={'quest_id': quest.id, 'start_from_user_id': 1}, queue='default')

    @patch('prerequisites.signals.update_conditions_for_quest.apply_async')
    def test_update_cache_triggered_by_parent_object_deletion(self, task):
        """When a quest is deleted it will cascade to delete any prereqs for which it is a parent.
        That shouldn't break this signal.
        """
        quest = baker.make('quest_manager.quest')
        baker.make(Prereq, prereq_invert=True, parent_object=quest)  # creation

        quest.delete()  # doesn't call task because parent_object no longer exists.
        self.assertEqual(task.call_count, 1)
