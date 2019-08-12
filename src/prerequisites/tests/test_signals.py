from django.contrib.auth import get_user_model
from django.test import TestCase
from freezegun import freeze_time
from mock import patch
from model_mommy import mommy

from badges.models import Badge, BadgeAssertion
from courses.models import CourseStudent, Semester
from prerequisites.models import Prereq
from quest_manager.models import Quest, QuestSubmission


User = get_user_model()


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class PrerequisitesSignalsTest(TestCase):

    def setUp(self):
        self.teacher = mommy.make(User, username='teacher', is_staff=True)
        self.student = mommy.make(User, username='student', is_staff=False)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_badge_assertion(self, task):
        sem = mommy.make(Semester)  # not sure why model mommy doesn't create this automatically
        badge_assertion = mommy.make(BadgeAssertion, user=self.student, game_lab_transfer=True, semester=sem)
        badge_assertion.game_lab_transfer = False
        badge_assertion.save()
        self.assertEqual(task.call_count, 2)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_quest_summission(self, task):
        quest_summission = mommy.make(QuestSubmission, user=self.student, is_completed=False)
        quest_summission.is_completed = True
        quest_summission.save()
        self.assertEqual(task.call_count, 2)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_course_student(self, task):
        with patch('profile_manager.models.Profile.xp_invalidate_cache') as callback:
            course_student = mommy.make(CourseStudent, user=self.student, active=False)
            course_student.active = True
            course_student.save()
            self.assertEqual(task.call_count, 2)
            self.assertEqual(callback.call_count, 2)

    @patch('prerequisites.signals.update_quest_conditions_all.apply_async')
    def test_update_quest_conditions_triggered_by_badge(self, task):
        badge = mommy.make(Badge, active=True)
        badge.active = False
        badge.save()
        self.assertEqual(task.call_count, 2)

    @patch('prerequisites.signals.update_conditions_for_quest.apply_async')
    def test_update_quest_conditions_triggered_by_quest(self, task):
        quest = mommy.make(Quest, verification_required=True)
        quest.verification_required = False
        quest.save()
        self.assertEqual(task.call_count, 2)

    @patch('prerequisites.signals.update_quest_conditions_all.apply_async')
    def test_update_quest_conditions_triggered_by_prereq(self, task):
        prereq = mommy.make(Prereq, prereq_invert=True)
        prereq.prereq_invert = False
        prereq.save()
        self.assertEqual(task.call_count, 2)
