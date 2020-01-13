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
import djconfig


User = get_user_model()


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class QuestManagerTest(TestCase):

    def setUp(self):
        djconfig.reload_maybe()  # https://github.com/nitely/django-djconfig/issues/31#issuecomment-451587942
        self.teacher = mommy.make(User, username='teacher', is_staff=True)
        self.student = mommy.make(User, username='student', is_staff=False)

    def test_quest_qs_exclude_hidden(self):
        """QuestQuerySet.datetime_available should return all quests that are not 
        on a user profile's hidden quest list."""

        mommy.make(Quest, name='Quest-not-hidden')
        mommy.make(Quest, name='Quest-also-not-hidden')
        quest1_to_hide = mommy.make(Quest, name='Quest1-hidden')
        quest2_to_hide = mommy.make(Quest, name='Quest2-hidden')

        qs = Quest.objects.order_by('id').exclude_hidden(self.student).values_list('name', flat=True)
        expected_result = ['Quest-not-hidden', 'Quest-also-not-hidden', 'Quest1-hidden', 'Quest2-hidden'] 
        # Nothing hidden yet
        self.assertListEqual(list(qs), expected_result)     

        self.student.profile.hide_quest(quest1_to_hide.id)
        self.student.profile.hide_quest(quest2_to_hide.id)

        qs = Quest.objects.order_by('id').exclude_hidden(self.student).values_list('name', flat=True)
        expected_result = ['Quest-not-hidden', 'Quest-also-not-hidden']
        # a couple hidden
        self.assertListEqual(list(qs), expected_result) 

    def test_quest_qs_block_if_needed(self):
        """QuestQuerySet.block_if_needed should return only blocking quests if one or more exist,
        otherwise, return full qs """
        mommy.make(Quest, name='Quest-blocking', blocking=True)
        mommy.make(Quest, name='Quest-also-blocking', blocking=True)
        mommy.make(Quest, name='Quest-not-blocked')

        qs = Quest.objects.order_by('id').block_if_needed()
        expected_result = ['Quest-blocking', 'Quest-also-blocking'] 
        self.assertListEqual(list(qs.values_list('name', flat=True)), expected_result) 

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

    def test_quest_qs_get_list_not_submitted_or_inprogress(self):
        """
        QuestQuerySet.get_list_not_submitted_or_inprogress should return quests that 
        have not been started (in progress or submitted for completion), 
        or if it has been completed already, that it is a repeatable quest past the repeat time
        """        
        quest_1hr_cooldown, quest_not_started, _ = self.make_test_quests_and_submissions_stack()

        # jump ahead an hour so repeat cooldown is over
        with freeze_time(localtime() + timedelta(hours=1, minutes=1)):
            list_not_started = Quest.objects.all().get_list_not_submitted_or_inprogress(self.student)
        self.assertListEqual(list_not_started, [quest_1hr_cooldown, quest_not_started])

    def test_quest_qs_not_submitted_or_inprogress(self):
        quest_1hr_cooldown, quest_not_started, _ = self.make_test_quests_and_submissions_stack()

        # jump ahead an hour so repeat cooldown is over
        with freeze_time(localtime() + timedelta(hours=1, minutes=1)):
            not_started = Quest.objects.all().not_submitted_or_inprogress(self.student)
        self.assertListEqual(list(not_started), [quest_1hr_cooldown, quest_not_started])

    def test_quest_qs_not_completed(self):
        """Should return all the quests that do NOT have a completed submission"""
        _, _, active_semester = self.make_test_quests_and_submissions_stack()
        with patch('quest_manager.models.config') as cfg:
            cfg.hs_active_semester = active_semester
            qs = Quest.objects.order_by('id').not_completed(self.student)
        expected_result = ['Quest-inprogress-sem2', 'Quest-not-started', 'Quest-inprogress']
        self.assertListEqual(list(qs.values_list('name', flat=True)), expected_result)   

    def test_quest_qs_not_in_progress(self):
        """Should return all the quests that do NOT have an inprogress submission"""
        _, _, active_semester = self.make_test_quests_and_submissions_stack()
        with patch('quest_manager.models.config') as cfg:
            cfg.hs_active_semester = active_semester
            qs = Quest.objects.order_by('id').not_in_progress(self.student)
        expected_result = ['Quest-completed-sem2', 'Quest-not-started', 'Quest-completed', 'Quest-1hr-cooldown']
        self.assertListEqual(list(qs.values_list('name', flat=True)), expected_result)

    def test_quest_manager_get_available(self):
        """ DESCRIPTION FROM METHOD:
        Quests that should appear in the user's Available quests tab.   Should exclude:
        1. Quests whose available date & time has not past, or quest that have expired
        2. Quests that are not visible to students or archived
        3. Quests who's prerequisites have not been met
        4. Quests that are not currently submitted for approval or already in progress <<<< COVERED HERE
        5. Quests who's maximum repeats have been completed
        6. Quests who's repeat time has not passed since last completion <<<< COVERED HERE
        """
        _, _, active_semester = self.make_test_quests_and_submissions_stack()
        with patch('quest_manager.models.config') as cfg:
            cfg.hs_active_semester = active_semester
            qs = Quest.objects.get_available(self.student)
        self.assertListEqual(list(qs.values_list('name', flat=True)), ['Quest-not-started'])  

    def make_test_quests_and_submissions_stack(self):
        """  Creates 6 quests with related submissions
        Quest                   sub     .completed   .semester
        Quest-inprogress-sem2   Y       False        2
        Quest-completed-sem2    Y       True         2
        Quest-not-started       N       NA           NA          
        Quest-inprogress        Y       False        1
        Quest-completed         Y       True         1
        Quest-1hr-cooldown      Y       True         1
        """

        quest_inprog_sem2 = mommy.make(Quest, name='Quest-inprogress-sem2')
        sub_inprog_sem2 = mommy.make(QuestSubmission, user=self.student, quest=quest_inprog_sem2)
        sem2 = sub_inprog_sem2.semester
        quest_complete_sem2 = mommy.make(Quest, name='Quest-completed-sem2')
        sub_complete_sem2 = mommy.make(QuestSubmission, user=self.student, quest=quest_complete_sem2, semester=sem2)
        sub_complete_sem2.mark_completed()

        quest_not_started = mommy.make(Quest, name='Quest-not-started')
        quest_inprogress = mommy.make(Quest, name='Quest-inprogress')
        first_sub = mommy.make(QuestSubmission, user=self.student, quest=quest_inprogress)
        active_semester = first_sub.semester
        quest_completed = mommy.make(Quest, name='Quest-completed')
        sub_complete = mommy.make(QuestSubmission, user=self.student, quest=quest_completed, semester=active_semester)
        sub_complete.mark_completed()
        quest_1hr_cooldown = mommy.make(Quest, name='Quest-1hr-cooldown', max_repeats=1, hours_between_repeats=1)
        sub_cooldown_complete = mommy.make(QuestSubmission, user=self.student, quest=quest_1hr_cooldown, semester=active_semester)  # noqa
        sub_cooldown_complete.mark_completed()
        return quest_1hr_cooldown, quest_not_started, active_semester


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class QuestSubmissionQuerysetTest(TestCase):

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


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class QuestSubmissionManagerTest(TestCase):

    def setUp(self):
        self.teacher = mommy.make(User, username='teacher', is_staff=True)
        self.student = mommy.make(User, username='student', is_staff=False)

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
