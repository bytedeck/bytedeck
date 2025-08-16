from django.contrib.auth import get_user_model

from django.contrib.contenttypes.models import ContentType
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from freezegun import freeze_time
from unittest.mock import patch
from model_bakery import baker

from badges.models import Badge, BadgeAssertion
from courses.models import CourseStudent, Semester
from prerequisites.models import Prereq
from quest_manager.models import Quest, QuestSubmission
from djcytoscape.models import CytoScape
from siteconfig.models import SiteConfig

User = get_user_model()


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class PrerequisitesSignalsTest(TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.teacher = baker.make(User, username='teacher', is_staff=True)
        self.student = baker.make(User, username='student', is_staff=False)

        self.sem = baker.make(Semester)
        self.badge_assertion = baker.make(BadgeAssertion,
                                          user=self.student,
                                          do_not_grant_xp=True,
                                          semester=self.sem)
        self.quest_submission = baker.make(QuestSubmission,
                                           user=self.student,
                                           is_completed=False)

        self.course_student = baker.make(CourseStudent,
                                         user=self.student,
                                         active=False)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_badge_assertion_on_create(self, task):
        """
        Creation of a new badge assertion (granting a badge to a student) should trigger a signal
        """
        baker.make(BadgeAssertion, user=self.student, do_not_grant_xp=True, semester=self.sem)
        self.assertEqual(task.call_count, 1)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_badge_assertion_on_update(self, task):
        """
        Updating a new badge assertion (granting a badge to a student) should trigger a signal
        """
        self.badge_assertion.do_not_grant_xp = False
        self.badge_assertion.save()
        self.assertEqual(task.call_count, 1)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_quest_summission_on_create(self, task):
        """
        Creation of a new quest_submission (when starting a quest) should NOT trigger a signal
        """
        baker.make(QuestSubmission, user=self.student, is_completed=False)
        self.assertEqual(task.call_count, 0)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_quest_summission_on_update(self, task):
        """
        Updating a quest_submission (when completing a quest) should trigger a signal
        """
        self.quest_submission.is_approved = True
        self.quest_submission.is_completed = True
        self.quest_submission.save()
        self.assertEqual(task.call_count, 1)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_course_student_on_create(self, task):
        with patch('profile_manager.models.Profile.xp_invalidate_cache') as callback:
            baker.make(CourseStudent, user=self.student, active=False)
            self.assertEqual(task.call_count, 1)
            self.assertEqual(callback.call_count, 1)

    @patch('prerequisites.signals.update_quest_conditions_for_user.apply_async')
    def test_update_conditions_met_for_user_triggered_by_course_student_on_update(self, task):
        with patch('profile_manager.models.Profile.xp_invalidate_cache') as callback:
            self.course_student.active = True
            self.course_student.save()
            self.assertEqual(task.call_count, 1)
            self.assertEqual(callback.call_count, 1)

    @patch('prerequisites.signals.update_quest_conditions_all_users.apply_async')
    def test_update_prereq_cache_triggered_by_badge(self, task):
        """
        Creation and Update of a prereq where the parent is not a quest should not trigger a cache update
        """
        badge = baker.make(Badge, published=True)  # creation
        badge.published = False
        badge.save()  # update
        self.assertEqual(task.call_count, 2)

    @patch('prerequisites.signals.update_quest_conditions_all_users.apply_async')
    def test_update_cache_triggered_by_quest_without_prereqs(self, task):
        """
        Creation and Update of a Quest without a prerequisite should trigger a cache update
        """
        quest = baker.make(Quest)   # creation
        quest.verification_required = False
        quest.save()  # update
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
    def test_update_prereq_cache_triggered_by_quest_available_outside_course(self, task):
        """Creation and Update of a quest should trigger a cache update, only when it is available outside the course.
        """
        quest = baker.make(Quest, verification_required=True)  # creation
        quest.available_outside_course = True
        quest.save()  # update
        self.assertEqual(task.call_count, 1)

    @patch('prerequisites.signals.update_conditions_for_quest.apply_async')
    def test_update_cache_triggered_by_non_quest_prereq(self, task):
        """
        Creation and Update of a prereq where the parent is not a quest should not trigger a cache update
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

    @patch('djcytoscape.tasks.regenerate_map.apply_async')
    def test_prereq_regenerate_related_maps(self, task):
        """ Tests if saving and deleting quest triggers `regenerate_map` task.
        Cant check if `regenerate_map` made new CytoElements. So checking if task args are accurate
        """
        # setup a simple map
        # origin -> quest
        origin = baker.make('quest_manager.quest', name='origin')
        quest = baker.make('quest_manager.quest', name='quest')
        prereq = Prereq.add_simple_prereq(quest, origin)
        scape = CytoScape.generate_map(origin, "Map")

        # should regenerate map on save
        prereq.save()
        self.assertEqual(task.call_count, 1)
        self.assertEqual(task.call_args.kwargs['args'][0], [scape.id])

        # should regenerate map on delete
        prereq.delete()
        self.assertEqual(task.call_count, 2)
        self.assertEqual(task.call_args.kwargs['args'][0], [scape.id])

        # test if task fires if map_auto_update is on
        sc = SiteConfig.get()
        sc.map_auto_update = False
        sc.save()

        prereq.save()
        self.assertEqual(task.call_count, 2)

    def test_on_quest_badge_save_with_rank_prereq__creation(self):
        """  Test that creating a Prereq, where either the prereq_object or the or_prereq_object are a Rank,
        results in the generation of a new CytoScape map with the Rank as the map's initial_object.

        Prereq - the model (a group of conditions)
        prereq_object - the actual prerequisite that needs to be met
        or_prereq_object - the alternate prerequisite.
        """

        # create prereq with rank as the first prereq
        # and check if new map is created
        first_rank = baker.make('courses.rank', name='first rank')
        baker.make(
            Prereq,
            parent_object=baker.make('quest_manager.quest'),
            prereq_object=first_rank,
        )

        self.assertTrue(CytoScape.objects.filter(
            name=f'{first_rank.name} Map',
            initial_content_type=ContentType.objects.get_for_model(first_rank),
            initial_object_id=first_rank.id,
        ).exists())

        # create prereq with rank as the alternative prereq
        # and check if new map is created
        second_rank = baker.make('courses.rank', name='second rank')
        baker.make(
            Prereq,
            parent_object=baker.make('quest_manager.quest'),
            or_prereq_object=second_rank,
        )

        self.assertTrue(CytoScape.objects.filter(
            name=f'{second_rank.name} Map',
            initial_content_type=ContentType.objects.get_for_model(second_rank),
            initial_object_id=second_rank.id,
        ).exists())

        # check if rank with a preexisting map isnt created
        third_rank = baker.make('courses.rank', name='third rank')
        CytoScape.generate_map(
            initial_object=third_rank,
            name='Pre-Existing Map',
        )
        baker.make(
            Prereq,
            parent_object=baker.make('quest_manager.quest'),
            prereq_object=third_rank,
        )
        # assert only 1 map exist
        self.assertEqual(CytoScape.objects.filter(
            initial_content_type=ContentType.objects.get_for_model(third_rank),
            initial_object_id=third_rank.id,
        ).count(), 1)

        # check if `invert=True` doesn't make a map
        no_map = baker.make('courses.rank', name='no map rank')
        baker.make(
            Prereq,
            prereq_invert=True,
            parent_object=baker.make('quest_manager.quest'),
            prereq_object=no_map,
        )

        self.assertFalse(CytoScape.objects.filter(
            name=f'{no_map.name} Map',
            initial_content_type=ContentType.objects.get_for_model(no_map),
            initial_object_id=no_map.id,
        ).exists())
