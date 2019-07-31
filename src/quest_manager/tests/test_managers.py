# import djconfig
from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from model_mommy import mommy
# from model_mommy.recipe import Recipe
from freezegun import freeze_time
from quest_manager.models import Quest, QuestSubmission
from courses.models import Semester
from django.utils.timezone import localtime
from mock import patch


User = get_user_model()


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class QuestManagerTest(TestCase):

    def test_quest_qs_datetime_available(self):
        """QuestQuerySet.datetime_available should return quests available for curent"""
        cur_datetime = localtime()
        cur_date = cur_datetime.date()
        time_now = cur_datetime.time()
        time_earlier = (cur_datetime - timedelta(hours=1)).time()
        time_later = (cur_datetime + timedelta(hours=1)).time()
        yesterday = (cur_datetime - timedelta(days=1)).date()
        tomorrow = (cur_datetime + timedelta(days=1)).date()

        # available_quests:
        mommy.make(Quest, name='Quest-curent', date_available=cur_date, time_available=time_now)
        mommy.make(Quest, name='Quest-later-today', date_available=cur_date, time_available=time_later)
        mommy.make(Quest, name='Quest-tomorrow', date_available=tomorrow, time_available=time_earlier)

        # not available quests:
        mommy.make(Quest, name='Quest-earlier-today', date_available=cur_date, time_available=time_earlier)
        mommy.make(Quest, name='Quest-yesterday', date_available=yesterday, time_available=time_later)

        qs = Quest.objects.order_by('id').datetime_available().values_list('name', flat=True)
        self.assertListEqual(list(qs), ['Quest-curent', 'Quest-earlier-today', 'Quest-yesterday'])

    def test_quest_qs_not_expired(self):
        """
        QuestQuerySet.not_expired should return not expired quests including:
            If date_expired and time_expired are null: quest never expires
            If date_expired exists, but time_expired is null: quest expires after the date (midnight)
            If date_expired and time_expired exist: thing expires on that date, after the time
            If only time_expired exists: thing expires after the time, daily
                (so would become not expired again at midnight when time = 00:00:00)
        """
        cur_datetime = localtime()
        cur_date = cur_datetime.date()
        time_now = cur_datetime.time()
        time_earlier = (cur_datetime - timedelta(hours=1)).time()
        time_later = (cur_datetime + timedelta(hours=1)).time()
        yesterday = (cur_datetime - timedelta(days=1)).date()
        tomorrow = (cur_datetime + timedelta(days=1)).date()

        # not expired quests:
        mommy.make(Quest, name='Quest-never-expired', date_expired=None, time_expired=None)
        # TODO: should quest whish expires now be available as not expired ???
        mommy.make(Quest, name='Quest-expired-now', date_expired=cur_date, time_expired=time_now)
        mommy.make(Quest, name='Quest-expired-today-midnight', date_expired=cur_date, time_expired=None)
        mommy.make(Quest, name='Quest-expired-tomorrow', date_expired=tomorrow, time_expired=time_earlier)

        # expired quests:
        mommy.make(Quest, name='Quest-expired-earlier-today', date_expired=cur_date, time_expired=time_earlier)
        mommy.make(Quest, name='Quest-expired-yesterday', date_expired=yesterday, time_expired=time_later)
        mommy.make(Quest, name='Quest-expired-by-time', date_expired=None, time_expired=time_earlier)

        qs = Quest.objects.order_by('id').not_expired().values_list('name', flat=True)
        result = ['Quest-never-expired', 'Quest-expired-now', 'Quest-expired-today-midnight', 'Quest-expired-tomorrow']
        self.assertListEqual(list(qs), result)

    def test_quest_qs_visible(self):
        """QuestQuerySet.visible should return visible for students quests"""
        mommy.make(Quest, name='Quest-visible', visible_to_students=True)
        mommy.make(Quest, name='Quest-invisible', visible_to_students=False)
        self.assertListEqual(list(Quest.objects.all().visible().values_list('name', flat=True)), ['Quest-visible'])

    def test_quest_qs_not_archived(self):
        """QuestQuerySet.not_archived should return not_archived quests"""
        mommy.make(Quest, name='Quest-not-archived', archived=False)
        mommy.make(Quest, name='Quest-archived', archived=True)
        qs = Quest.objects.all().not_archived().values_list('name', flat=True)
        self.assertListEqual(list(qs), ['Quest-not-archived'])

    def test_quest_qs_available_without_course(self):
        """QuestQuerySet.available_without_course should return quests available_outside_course"""
        mommy.make(Quest, name='Quest-available-without-course', available_outside_course=True)
        mommy.make(Quest, name='Quest-not-available-without-course', available_outside_course=False)
        qs = Quest.objects.all().available_without_course().values_list('name', flat=True)
        self.assertListEqual(list(qs), ['Quest-available-without-course'])

    def test_quest_qs_editable(self):
        """
        QuestQuerySet.editable should return quests allowed to edit for given user,
        when user is_staff or editor for the quest
        """
        teacher = mommy.make(User, is_staff=True)
        student1 = mommy.make(User, is_staff=False)
        student2 = mommy.make(User, is_staff=False)
        mommy.make(Quest, name='Quest-editable-for-student1', editor=student1)
        mommy.make(Quest, name='Quest-editable-for-teacher', editor=teacher)
        self.assertEqual(Quest.objects.all().editable(teacher).count(), 2)
        self.assertEqual(Quest.objects.all().editable(student1).count(), 1)
        self.assertEqual(Quest.objects.all().editable(student2).count(), 0)


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class QuestSubmissionTest(TestCase):

    def setUp(self):
        self.teacher = mommy.make(User, username='teacher', is_staff=True)
        self.student = mommy.make(User, username='student', is_staff=False)

    def test_quest_submission_qs_get_user(self):
        """QuestSubmissionQuerySet.get_user should return all quest submissions for given user"""
        first = mommy.make(QuestSubmission, user=self.student)
        mommy.make(QuestSubmission, user=self.teacher)
        mommy.make(QuestSubmission)
        qs = QuestSubmission.objects.all().get_user(self.student).values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id])

    def test_quest_submission_qs_get_quest(self):
        """QuestSubmissionQuerySet.get_quest should return all quest submissions for given quest"""
        quest = mommy.make(Quest, name='Sub')
        first, second = mommy.make(QuestSubmission, quest=quest), mommy.make(QuestSubmission, quest=quest)
        mommy.make(QuestSubmission)
        qs = QuestSubmission.objects.order_by('id').get_quest(quest).values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id, second.id])

    def test_quest_submission_qs_get_semester(self):
        """QuestSubmissionQuerySet.get_semester should return all quest submissions for given semester"""
        semester = mommy.make(Semester, active=True)
        first = mommy.make(QuestSubmission, semester=semester)
        mommy.make(QuestSubmission)
        qs = QuestSubmission.objects.order_by('id').get_semester(semester).values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id])

    def test_quest_submission_qs_exclude_archived_quests(self):
        """
        QuestSubmissionQuerySet.exclude_archived_quests should return quest submissions
        without submissions for archived_quests
        """
        first = mommy.make(QuestSubmission, quest__archived=False)
        mommy.make(QuestSubmission, quest__archived=True)
        qs = QuestSubmission.objects.order_by('id').exclude_archived_quests().values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id])

    def test_quest_submission_qs_exclude_quests_not_visible_to_students(self):
        """
        QuestSubmissionQuerySet.exclude_quests_not_visible_to_students should return quest submissions
        without submissions for invisible quests
        """
        first = mommy.make(QuestSubmission, quest__visible_to_students=True)
        mommy.make(QuestSubmission, quest__visible_to_students=False)
        qs = QuestSubmission.objects.order_by('id').exclude_archived_quests().values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id])

    def test_quest_submission_manager_get_queryset_default(self):
        """QuestSubmissionManager.get_queryset should return all visible not archived quest submissions"""
        submissions = self.make_test_submissions_stack()
        with patch('quest_manager.models.config') as cfg:
            cfg.hs_active_semester = submissions[0].semester
            qs = QuestSubmission.objects.get_queryset().order_by('id').values_list('id', flat=True)
        self.assertListEqual(list(qs), [submissions[0].id, submissions[1].id])

    def test_quest_submission_manager_get_queryset_for_active_semester(self):
        submissions = self.make_test_submissions_stack()
        with patch('quest_manager.models.config') as cfg:
            cfg.hs_active_semester = submissions[0].semester
            qs = QuestSubmission.objects.get_queryset(active_semester_only=True).values_list('id', flat=True)
        self.assertListEqual(list(qs), [submissions[0].id])

    def test_quest_submission_manager_get_queryset_for_all_quests(self):
        submissions = self.make_test_submissions_stack()
        with patch('quest_manager.models.config') as cfg:
            cfg.hs_active_semester = submissions[0].semester
            qs = QuestSubmission.objects.get_queryset(
                exclude_archived_quests=False, exclude_quests_not_visible_to_students=False)
        self.assertEqual(qs.count(), 7)

    def test_quest_submission_manager_all_for_user_quest(self):
        """
        QuestSubmissionManager.all_for_user_quest should return all visible not archived quest submissions
        for active semester, given user and quest
        """
        submissions = self.make_test_submissions_stack()
        active_semester = submissions[0].semester
        quest = submissions[0].quest
        first = mommy.make(QuestSubmission, user=self.student, quest=quest, semester=active_semester)
        with patch('quest_manager.models.config') as cfg:
            cfg.hs_active_semester = active_semester
            qs = QuestSubmission.objects.all_for_user_quest(self.student, quest, True).values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id])

    def make_test_submissions_stack(self):
        active = mommy.make(Semester, active=True)
        inactive = mommy.make(Semester, active=False)
        quest1 = mommy.make(QuestSubmission, quest__visible_to_students=True, quest__archived=False, semester=active)
        mommy.make(QuestSubmission, quest__visible_to_students=False, quest__archived=False, semester=active)
        mommy.make(QuestSubmission, quest__visible_to_students=True, quest__archived=True, semester=active)
        quest2 = mommy.make(QuestSubmission, quest__visible_to_students=True, quest__archived=False, semester=inactive)
        mommy.make(QuestSubmission, quest__visible_to_students=False, quest__archived=True, semester=inactive)
        mommy.make(QuestSubmission, quest__visible_to_students=False, quest__archived=False, semester=inactive)
        mommy.make(QuestSubmission, quest__visible_to_students=True, quest__archived=True, semester=inactive)
        return quest1, quest2
