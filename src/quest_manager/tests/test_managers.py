from datetime import datetime, timedelta, timezone

from django.contrib.auth import get_user_model
from django.utils.timezone import localtime
# from django.test import tag
from freezegun import freeze_time
from model_bakery import baker

from courses.models import Semester
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig
from django_tenants.test.cases import TenantTestCase

User = get_user_model()


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class QuestManagerTest(TenantTestCase):

    def setUp(self):
        # get a list all quests created in data migrations
        # convert to list for ease of comparison, and also to force
        #  evaluation before additional quests are created within tests
        self.initial_quest_list = list(Quest.objects.all())
        # print(self.initial_quest_list)
        self.initial_quest_name_list = list(Quest.objects.all().values_list('name', flat=True))
        # this includes 6 quests, all visible to students, but only one
        # available at the start as the rest have prerequisites.

        self.teacher = baker.make(User, username='teacher', is_staff=True)
        self.student = baker.make(User, username='student', is_staff=False)
        self.maxDiff = None

    def test_quest_qs_exclude_hidden(self):
        """QuestQuerySet.datetime_available should return all quests that are not
        on a user profile's hidden quest list."""

        baker.make(Quest, name='Quest-not-hidden')
        baker.make(Quest, name='Quest-also-not-hidden')
        quest1_to_hide = baker.make(Quest, name='Quest1-hidden')
        quest2_to_hide = baker.make(Quest, name='Quest2-hidden')

        qs = Quest.objects.order_by('id').exclude_hidden(self.student).values_list('name', flat=True)
        expected_result = ['Quest-not-hidden', 'Quest-also-not-hidden', 'Quest1-hidden', 'Quest2-hidden'] + self.initial_quest_name_list
        # Nothing hidden yet (use set so order doesn't matter)
        self.assertSetEqual(set(qs), set(expected_result))

        self.student.profile.hide_quest(quest1_to_hide.id)
        self.student.profile.hide_quest(quest2_to_hide.id)

        qs = Quest.objects.order_by('id').exclude_hidden(self.student).values_list('name', flat=True)
        expected_result = ['Quest-not-hidden', 'Quest-also-not-hidden'] + self.initial_quest_name_list
        # a couple hidden
        self.assertSetEqual(set(qs), set(expected_result))

    def test_quest_qs_block_if_needed(self):
        """QuestQuerySet.block_if_needed should return only blocking quests if one or more exist,
        otherwise, return full qs """
        baker.make(Quest, name='Quest-blocking', blocking=True)
        baker.make(Quest, name='Quest-also-blocking', blocking=True)
        baker.make(Quest, name='Quest-not-blocked')

        qs = Quest.objects.order_by('id').block_if_needed()
        expected_result = ['Quest-blocking', 'Quest-also-blocking']
        self.assertListEqual(list(qs.values_list('name', flat=True)), expected_result)

        # Test the user specific part via QuestManager.get_available test"

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
        baker.make(Quest, name='Quest-curent', date_available=cur_date, time_available=time_now)
        baker.make(Quest, name='Quest-later-today', date_available=cur_date, time_available=time_later)
        baker.make(Quest, name='Quest-tomorrow', date_available=tomorrow, time_available=time_earlier)

        # not available quests:
        baker.make(Quest, name='Quest-earlier-today', date_available=cur_date, time_available=time_earlier)
        baker.make(Quest, name='Quest-yesterday', date_available=yesterday, time_available=time_later)

        qs = Quest.objects.order_by('id').datetime_available().values_list('name', flat=True)
        self.assertSetEqual(
            set(qs),
            set(['Quest-curent', 'Quest-earlier-today', 'Quest-yesterday'] + self.initial_quest_name_list)
        )

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
        baker.make(Quest, name='Quest-never-expired', date_expired=None, time_expired=None)
        # TODO: should quest whish expires now be available as not expired ???
        baker.make(Quest, name='Quest-expired-now', date_expired=cur_date, time_expired=time_now)
        baker.make(Quest, name='Quest-expired-today-midnight', date_expired=cur_date, time_expired=None)
        baker.make(Quest, name='Quest-expired-tomorrow', date_expired=tomorrow, time_expired=time_earlier)

        # expired quests:
        baker.make(Quest, name='Quest-expired-earlier-today', date_expired=cur_date, time_expired=time_earlier)
        baker.make(Quest, name='Quest-expired-yesterday', date_expired=yesterday, time_expired=time_later)
        baker.make(Quest, name='Quest-expired-by-time', date_expired=None, time_expired=time_earlier)

        qs = Quest.objects.order_by('id').not_expired().values_list('name', flat=True)
        result = ['Quest-never-expired', 'Quest-expired-now', 'Quest-expired-today-midnight', 'Quest-expired-tomorrow']
        self.assertSetEqual(set(qs), set(result + self.initial_quest_name_list))

    def test_quest_qs_visible(self):
        """QuestQuerySet.visible should return visible for students quests"""
        # baker.make(Quest, name='Quest-visible', visible_to_students=True)
        baker.make(Quest, name='Quest-invisible', visible_to_students=False)
        # self.assertListEqual(list(Quest.objects.all().visible().values_list('name', flat=True)), ['Quest-visible'])
        self.assertListEqual(list(Quest.objects.all().visible()), self.initial_quest_list)

    def test_quest_qs_not_archived(self):
        """QuestQuerySet.not_archived should return not_archived quests"""
        baker.make(Quest, name='Quest-not-archived', archived=False)
        baker.make(Quest, name='Quest-archived', archived=True)
        qs = Quest.objects.all().not_archived().values_list('name', flat=True)
        self.assertSetEqual(set(qs), set(['Quest-not-archived'] + self.initial_quest_name_list))

    def test_quest_qs_available_without_course(self):
        """QuestQuerySet.available_without_course should return quests available_outside_course"""
        baker.make(Quest, name='Quest-available-without-course', available_outside_course=True)
        baker.make(Quest, name='Quest-not-available-without-course', available_outside_course=False)
        qs = Quest.objects.all().available_without_course().values_list('name', flat=True)
        self.assertQuerysetEqual(qs, ['Quest-available-without-course', 'Send your teacher a Message'], ordered=False)

    def test_quest_qs_editable(self):
        """
        QuestQuerySet.editable should return quests allowed to edit for given user,
        when user is_staff or editor for the quest
        """
        teacher = baker.make(User, is_staff=True)
        student1 = baker.make(User, is_staff=False)
        student2 = baker.make(User, is_staff=False)
        baker.make(Quest, name='Quest-editable-for-student1', editor=student1)
        baker.make(Quest, name='Quest-editable-for-teacher', editor=teacher)
        self.assertEqual(Quest.objects.all().editable(teacher).count(), 2 + len(self.initial_quest_list))
        self.assertEqual(Quest.objects.all().editable(student1).count(), 1)
        self.assertEqual(Quest.objects.all().editable(student2).count(), 0)

    # def test_quest_qs_get_list_not_submitted_or_inprogress(self):
    #     """
    #     QuestQuerySet.get_list_not_submitted_or_inprogress should return quests that
    #     have not been started (in progress or submitted for approval),
    #     or if it has been completed already, that it is a repeatable quest past the repeat time
    #     """
    #     self.make_test_quests_and_submissions_stack()

    #     # jump ahead an hour so repeat cooldown is over
    #     with freeze_time(localtime() + timedelta(hours=1, minutes=1)):
    #         qs = Quest.objects.all().get_list_not_submitted_or_inprogress(self.student)
    #     self.assertListEqual(
    #         list(qs.values_list('name', flat=True)),
    #         ['Quest-1hr-cooldown', 'Quest-blocking', 'Quest-not-started']
    #     )

    def test_quest_qs_not_submitted_or_inprogress(self):
        self.make_test_quests_and_submissions_stack()

        # jump ahead an hour so repeat cooldown is over
        with freeze_time(localtime() + timedelta(hours=1, minutes=1)):
            qs = Quest.objects.all().not_submitted_or_inprogress(self.student)
        # compare sets so order doesn't matter
        self.assertSetEqual(
            set(qs.values_list('name', flat=True)),
            set(['Quest-1hr-cooldown', 'Quest-blocking', 'Quest-not-started'] + self.initial_quest_name_list)
        )

    def test_quest_qs_not_completed(self):
        """Should return all the quests that do NOT have a completed submission (during active semester)"""
        active_semester = self.make_test_quests_and_submissions_stack()
        SiteConfig.get().set_active_semester(active_semester.id)
        qs = Quest.objects.order_by('id').not_completed(self.student)
        # compare sets so order doesn't matter
        self.assertSetEqual(
            set(qs.values_list('name', flat=True)),
            set(
                ['Quest-inprogress-sem2', 'Quest-completed-sem2', 'Quest-not-started', 'Quest-blocking', 'Quest-inprogress']
                + self.initial_quest_name_list
            )
        )

    def test_quest_qs_not_in_progress(self):
        """Should return all the quests that do NOT have an inprogress submission (during active semester)"""
        active_semester = self.make_test_quests_and_submissions_stack()
        SiteConfig.get().set_active_semester(active_semester.id)
        qs = Quest.objects.order_by('id').not_in_progress(self.student)
        # compare sets so order doesn't matter
        self.assertSetEqual(
            set(qs.values_list('name', flat=True)),
            set(['Quest-inprogress-sem2', 'Quest-completed-sem2', 'Quest-not-started', 'Quest-blocking', 'Quest-completed',
                 'Quest-1hr-cooldown'] + self.initial_quest_name_list)
        )

    def test_get_available(self):
        """ DESCRIPTION FROM METHOD:
        Quests that should appear in the user's Available quests tab.   Should exclude:
        1. Quests whose available date & time has not past, or quest that have expired
        2. Quests that are not visible to students or archived  <<<< COVERED HERE
        3. Quests that are a part of an inactive campaign/category <<<< COVERED HERE
        4. Quests who's prerequisites have not been met
        5. Quests that are not currently submitted for approval or already in progress <<<< COVERED HERE
        6. Quests who's maximum repeats have been completed <<<< COVERED HERE
        7. Quests who's repeat time has not passed since last completion <<<< COVERED HERE
        8. Check for blocking quests (available and in-progress), if present, remove all others <<<< COVERED HERE
        """

        active_semester = self.make_test_quests_and_submissions_stack()
        SiteConfig.get().set_active_semester(active_semester.id)

        # a couple additions just for this test:
        baker.make(Quest, name='Quest-expired', date_expired=(localtime() - timedelta(days=1)))  # 1
        baker.make(Quest, name='Quest-future', date_available=(localtime() + timedelta(days=1)))  # 1
        baker.make(Quest, name='Quest-not-visible', visible_to_students=False)  # 2
        baker.make(Quest, name='Quest-archived', archived=True)  # 2
        inactive_campaign = baker.make('quest_manager.Category', active=False)
        baker.make(Quest, name='Quest-inactive-campaign', campaign=inactive_campaign)  # 3

        ########################################
        # 8. Check for blocking quests (available and in-progress), if present, remove all others
        #########################################
        qs = Quest.objects.get_available(self.student)
        self.assertListEqual(list(qs.values_list('name', flat=True)), ['Quest-blocking'])

        # Start the blocking quest.
        blocking_quest = Quest.objects.get(name='Quest-blocking')
        blocking_sub = baker.make(QuestSubmission, quest=blocking_quest, user=self.student, semester=active_semester)

        # Should have no available quests while the blocking quest is in progress
        qs = Quest.objects.get_available(self.student)
        self.assertListEqual(list(qs.values_list('name', flat=True)), [])

        # complete the blocking quest to make others available
        blocking_sub.mark_completed()
        qs = Quest.objects.get_available(self.student)
        self.assertQuerysetEqual(list(qs.values_list('name', flat=True)), ['Quest-not-started', 'Welcome to ByteDeck!'], ordered=False)

        ########################################
        # 2. Quests that are not visible to students or archived
        #########################################
        # The assert above checks this condition, because these two do not appear:
        #  Quest-not-visible
        #  Quest-archived

        ########################################
        # 3. Quests that are a part of an inactive campaign
        ########################################
        # The assert above checks this condition, because this one don't appear:
        #  Quest-inactive-campaign

        ########################################
        # 5. Quests that are not currently submitted for approval or already in progress
        #########################################
        # The assert above checks this condition, because these two do not appear:
        #  Quest-inprogress
        #  Quest-completed

        #########################################
        # 7. Quests who's repeat time has not passed since last completion <<<< COVERED HERE
        #########################################
        # The assert above checks this condition, because this one don't appear:
        #  Quest-1hr-cooldown

        # move 1 hour out and the cooldown quest should now appear:
        with freeze_time(localtime() + timedelta(hours=1, minutes=1)):
            qs = Quest.objects.get_available(self.student)
            self.assertQuerysetEqual(
                list(qs.values_list('name', flat=True)),
                ['Quest-1hr-cooldown', 'Quest-not-started', 'Welcome to ByteDeck!'],
                ordered=False
            )

            #########################################
            # 6. Quests who's maximum repeats have been completed
            #########################################
            quest_1hr_cooldown = Quest.objects.get(name='Quest-1hr-cooldown')
            sub_1hr_cooldown = baker.make(QuestSubmission, quest=quest_1hr_cooldown, user=self.student, semester=active_semester)
            sub_1hr_cooldown.mark_completed()

            # increment time another hour just be sure it doesn't appear (max repeats of 1 reached)
            with freeze_time(localtime() + timedelta(hours=1, minutes=1)):
                qs = Quest.objects.get_available(self.student)
                self.assertQuerysetEqual(
                    list(qs.values_list('name', flat=True)),
                    ['Quest-1hr-cooldown', 'Quest-not-started', 'Welcome to ByteDeck!'],
                    ordered=False
                )

    def make_test_quests_and_submissions_stack(self):
        """  Creates 6 quests with related submissions
        Quest                   sub     .completed   .semester
        Quest-inprogress-sem2   Y       False        2
        Quest-completed-sem2    Y       True         2
        Quest-not-started       N       NA           NA
        Quest-inprogress        Y       False        1
        Quest-completed         Y       True         1
        Quest-1hr-cooldown      Y       True         1
        Quest-blocking          N       NA           NA

        Note that other quests automatically created in every deck will exist, like `Welcome to Bytedeck`

        """
        active_semester = baker.make(Semester)

        quest_inprog_sem2 = baker.make(Quest, name='Quest-inprogress-sem2')
        sub_inprog_sem2 = baker.make(QuestSubmission, user=self.student, quest=quest_inprog_sem2)
        sem2 = sub_inprog_sem2.semester
        quest_complete_sem2 = baker.make(Quest, name='Quest-completed-sem2')
        sub_complete_sem2 = baker.make(QuestSubmission, user=self.student, quest=quest_complete_sem2, semester=sem2)
        sub_complete_sem2.mark_completed()

        baker.make(Quest, name='Quest-not-started')
        baker.make(Quest, name='Quest-blocking', blocking=True)

        quest_inprogress = baker.make(Quest, name='Quest-inprogress')
        baker.make(QuestSubmission, user=self.student, quest=quest_inprogress, semester=active_semester)
        # active_semester = first_sub.semester
        quest_completed = baker.make(Quest, name='Quest-completed')
        sub_complete = baker.make(QuestSubmission, user=self.student, quest=quest_completed, semester=active_semester)
        sub_complete.mark_completed()
        quest_1hr_cooldown = baker.make(Quest, name='Quest-1hr-cooldown', max_repeats=1, hours_between_repeats=1)
        sub_cooldown_complete = baker.make(QuestSubmission, user=self.student, quest=quest_1hr_cooldown,
                                           semester=active_semester)  # noqa
        sub_cooldown_complete.mark_completed()

        return active_semester


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class QuestSubmissionQuerysetTest(TenantTestCase):

    def setUp(self):
        self.teacher = baker.make(User, username='teacher', is_staff=True)
        self.student = baker.make(User, username='student', is_staff=False)

    def test_quest_submission_qs_get_user(self):
        """QuestSubmissionQuerySet.get_user should return all quest submissions for given user"""
        first = baker.make(QuestSubmission, user=self.student)
        baker.make(QuestSubmission, user=self.teacher)
        baker.make(QuestSubmission)
        qs = QuestSubmission.objects.all().get_user(self.student).values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id])

    def test_quest_submission_qs_block_if_needed(self):
        """QuestSubmissionQuerySet.block_if_needed:
        if there are blocking quests, only return them.  Otherwise, return full qs """
        first = baker.make(QuestSubmission)

        # No blocking quests yet, so should be all
        qs = QuestSubmission.objects.all().block_if_needed().values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id])

        blocking_q = baker.make(Quest, blocking=True)
        blocked_sub = baker.make(QuestSubmission, quest=blocking_q)
        # Now block, only it should appear
        qs = QuestSubmission.objects.all().block_if_needed().values_list('id', flat=True)
        self.assertListEqual(list(qs), [blocked_sub.id])

    def test_quest_submission_qs_get_quest(self):
        """QuestSubmissionQuerySet.get_quest should return all quest submissions for given quest"""
        quest = baker.make(Quest, name='Sub')
        first, second = baker.make(QuestSubmission, quest=quest), baker.make(QuestSubmission, quest=quest)
        baker.make(QuestSubmission)
        qs = QuestSubmission.objects.order_by('id').get_quest(quest).values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id, second.id])

    def test_quest_submission_qs_get_semester(self):
        """QuestSubmissionQuerySet.get_semester should return all quest submissions for given semester"""
        semester = baker.make(Semester)
        first = baker.make(QuestSubmission, semester=semester)
        baker.make(QuestSubmission)
        qs = QuestSubmission.objects.order_by('id').get_semester(semester).values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id])

    def test_quest_submission_qs_exclude_archived_quests(self):
        """
        QuestSubmissionQuerySet.exclude_archived_quests should return quest submissions
        without submissions for archived_quests
        """
        first = baker.make(QuestSubmission, quest__archived=False)
        baker.make(QuestSubmission, quest__archived=True)
        qs = QuestSubmission.objects.order_by('id').exclude_archived_quests().values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id])

    def test_quest_submission_qs_exclude_quests_not_visible_to_students(self):
        """
        QuestSubmissionQuerySet.exclude_quests_not_visible_to_students should return quest submissions
        without submissions for invisible quests
        """
        first = baker.make(QuestSubmission, quest__visible_to_students=True)
        baker.make(QuestSubmission, quest__visible_to_students=False)
        qs = QuestSubmission.objects.order_by('id').exclude_archived_quests().values_list('id', flat=True)
        self.assertListEqual(list(qs), [first.id])

    def test_for_teacher_only(self):
        """Returned qs should only include sub my students in the teacher's block(s).  Also
        add a specific_teacher_to_notify and make sure that one appears too
        """

        self.quest = baker.make(Quest)
        self.active_semester = baker.make(Semester)
        self.sub = baker.make(QuestSubmission, user=self.student, quest=self.quest, semester=self.active_semester)
        SiteConfig.get().set_active_semester(self.active_semester.id)

        # Needs a course for the student, in a block with the teacher
        block = baker.make('courses.Block', current_teacher=self.teacher)
        baker.make('courses.CourseStudent', user=self.student, block=block, semester=self.active_semester)
        qs = QuestSubmission.objects.all()

        # Currently contains the submission from setup.
        self.assertQuerysetEqual(qs.for_teacher_only(self.teacher), [repr(self.sub)])

        # Add another submission from a different block, with a different teacher
        baker.make(QuestSubmission, quest=self.quest, semester=self.active_semester)
        # Should still only have the originally submission
        qs = QuestSubmission.objects.all()
        self.assertQuerysetEqual(qs.for_teacher_only(self.teacher), [repr(self.sub)])

        # Add another submission from a different block, but this time the quest should notify the teacher
        sub2 = baker.make(QuestSubmission, semester=self.active_semester, quest__specific_teacher_to_notify=self.teacher)
        # print(qs.for_teacher_only(self.teacher))
        qs = QuestSubmission.objects.all()
        self.assertQuerysetEqual(qs.for_teacher_only(self.teacher), [repr(self.sub), repr(sub2)], ordered=False)

    def test_for_teachers_only__with_deleted_quest(self):
        """for_teachers_only shouldn't break if a submission's quest has been deleted"""

        self.quest = baker.make(Quest)
        self.active_semester = baker.make(Semester)
        self.sub = baker.make(QuestSubmission, user=self.student, quest=self.quest, semester=self.active_semester)
        SiteConfig.get().set_active_semester(self.active_semester.id)

        # Needs a course for the student, in a block with the teacher
        block = baker.make('courses.Block', current_teacher=self.teacher)
        baker.make('courses.CourseStudent', user=self.student, block=block, semester=self.active_semester)

        self.quest.delete()
        qs = QuestSubmission.objects.all()
        self.assertQuerysetEqual(qs.for_teacher_only(self.teacher), ['<QuestSubmission: [DELETED QUEST]>'])

        # Add another submission from a different block, but this time the quest should notify the teacher
        quest2 = baker.make(Quest, specific_teacher_to_notify=self.teacher)
        sub2 = baker.make(QuestSubmission, semester=self.active_semester, quest=quest2)
        qs = QuestSubmission.objects.all()
        self.assertQuerysetEqual(qs.for_teacher_only(self.teacher), ['<QuestSubmission: [DELETED QUEST]>', repr(sub2)], ordered=False)

        # Delete this one too, shouldn't crash!
        quest2.delete()
        qs = QuestSubmission.objects.all()
        # Only has the first deleted sub, because the second one no longer has a quest.specific_teacher_to_notify, so not included.
        self.assertQuerysetEqual(qs.for_teacher_only(self.teacher), ['<QuestSubmission: [DELETED QUEST]>'])


@freeze_time('2018-10-12 00:54:00', tz_offset=0)
class QuestSubmissionManagerTest(TenantTestCase):

    def setUp(self):
        self.teacher = baker.make(User, username='teacher', is_staff=True)
        self.student = baker.make(User, username='student', is_staff=False)

        self.sub1, self.sub2 = self.make_test_submissions_stack()
        self.active_semester = self.sub1.semester
        SiteConfig.get().set_active_semester(self.active_semester.id)

    def test_get_queryset_default(self):
        """QuestSubmissionManager.get_queryset by default should return all visible, not archived quest submissions"""
        qs = QuestSubmission.objects.get_queryset()
        self.assertQuerysetEqual(qs, [repr(self.sub1), repr(self.sub2)], ordered=False)

    def test_get_queryset_for_active_semester(self):
        qs = QuestSubmission.objects.get_queryset(active_semester_only=True)
        self.assertQuerysetEqual(qs, [repr(self.sub1)])

    def test_get_queryset_for_all_quests(self):
        qs = QuestSubmission.objects.get_queryset(
            exclude_archived_quests=False, exclude_quests_not_visible_to_students=False)
        self.assertEqual(qs.count(), 7)

    def test_all_for_user_quest(self):
        """
        QuestSubmissionManager.all_for_user_quest should return all visible not archived quest submissions
        for active semester, given user and quest
        """
        quest = self.sub1.quest
        first = baker.make(QuestSubmission, user=self.student, quest=quest, semester=self.active_semester)
        qs = QuestSubmission.objects.all_for_user_quest(self.student, quest, True)
        self.assertQuerysetEqual(qs, [repr(first)])

    def make_test_submissions_stack(self):
        """Generate 7 submissions, 3 from one semester and 4 from a different semester, each with different settings

        Returns:
            [tuple]: the two submissions, one from each semester, where the quest is visible and not archived
        """
        semester = baker.make(Semester)
        another_semester = baker.make(Semester)

        sub1 = baker.make(QuestSubmission, quest__visible_to_students=True, quest__archived=False, semester=semester)
        baker.make(QuestSubmission, user=self.student, quest__visible_to_students=False, quest__archived=False, semester=semester)
        baker.make(QuestSubmission, user=self.student, quest__visible_to_students=True, quest__archived=True, semester=semester)

        sub2 = baker.make(QuestSubmission, quest__visible_to_students=True, quest__archived=False, semester=another_semester)
        baker.make(QuestSubmission, user=self.student, quest__visible_to_students=False, quest__archived=True, semester=another_semester)
        baker.make(QuestSubmission, user=self.student, quest__visible_to_students=False, quest__archived=False, semester=another_semester)
        baker.make(QuestSubmission, user=self.student, quest__visible_to_students=True, quest__archived=True, semester=another_semester)

        return sub1, sub2

    def test_calculate_xp(self):
        """QuestSubmissionManager.calculate_xp should return the correct amount of xp for some approved submissions"""

        # Create some approved submissions
        baker.make(QuestSubmission, user=self.student, semester=self.active_semester, is_approved=True, quest__xp=10)
        baker.make(QuestSubmission, user=self.student, semester=self.active_semester, is_approved=True, quest__xp=3)
        # There are already some unapproved submissions for this student from the submission stack created in SetUp
        xp = QuestSubmission.objects.calculate_xp(self.student)
        self.assertEqual(xp, 13)

    def test_calculate_xp_to_date(self):
        """QuestSubmissionManager.calculate_xp_to_date should not include xp earned up to and including the date.
        """
        # Create some approved submissions from after the `to_date``, should show up in XP
        baker.make(
            QuestSubmission, user=self.student, semester=self.active_semester, is_approved=True,
            quest__xp=10, time_approved=datetime(2017, 10, 13, tzinfo=timezone.utc)
        )
        xp = QuestSubmission.objects.calculate_xp_to_date(self.student, datetime(2017, 10, 12, tzinfo=timezone.utc))
        self.assertEqual(xp, 0)

        # Approve a sub on the same date and time, should show up in xp calculation
        baker.make(
            QuestSubmission, user=self.student, semester=self.active_semester, is_approved=True,
            quest__xp=3, time_approved=datetime(2017, 10, 12, tzinfo=timezone.utc)
        )
        xp = QuestSubmission.objects.calculate_xp_to_date(self.student, datetime(2017, 10, 12, tzinfo=timezone.utc))
        self.assertEqual(xp, 3)

    def test_calculate_xp__with_xp_requested(self):
        """If student can request a custom xp value for a submission, that xp should be properly included
        """
        # Create an approved submission
        baker.make(QuestSubmission, user=self.student, semester=self.active_semester, is_approved=True, quest__xp=10)

        # Create a submission with a custom XP value
        baker.make(QuestSubmission, user=self.student, semester=self.active_semester, is_approved=True, quest__xp=3, xp_requested=5)

        xp = QuestSubmission.objects.calculate_xp(self.student)
        # Should add the custom_xp value, if any.
        self.assertEqual(xp, 15)

    def test_calculate_xp__with_max_xp(self):
        """
        Student can complete quests that are availabe to them multiple times but they cannot earn xp more than the max_xp
        that can be gained in a repeatable quest
        """
        quest_repeatable_with_max_xp = baker.make(Quest, max_xp=15, xp=5, max_repeats=-1)
        baker.make(
            QuestSubmission, user=self.student, quest=quest_repeatable_with_max_xp,
            semester=self.active_semester, is_approved=True, _quantity=3
        )

        self.assertEqual(QuestSubmission.objects.calculate_xp(self.student), 15)

        # Perform additional submission but xp remains the same
        baker.make(QuestSubmission, user=self.student, quest=quest_repeatable_with_max_xp, semester=self.active_semester, is_approved=True)
        self.assertEqual(QuestSubmission.objects.calculate_xp(self.student), 15)

    def test_calculate_xp__ith_xp_requested_and_max_xp(self):
        """If student can request a custom xp value for a repeatable quest, the total xp shouldn't exceed the max_xp
        """
        # Create an approved submission
        baker.make(QuestSubmission, user=self.student, semester=self.active_semester, is_approved=True, quest__xp=10)

        # Create a repeatable quest with custom xp.
        quest = baker.make(Quest, xp=5, xp_can_be_entered_by_students=True, max_repeats=-1, max_xp=17)
        # submission with a custom XP values
        baker.make(QuestSubmission, quest=quest, user=self.student, semester=self.active_semester, is_approved=True, xp_requested=8)
        baker.make(QuestSubmission, quest=quest, user=self.student, semester=self.active_semester, is_approved=True, xp_requested=10)

        xp = QuestSubmission.objects.calculate_xp(self.student)
        # Should be the max_xp value + 10 (17+10) = 27), since request XP 10 + 8 = 18 is greater than the max_xp of 17
        self.assertEqual(xp, 27)

        # Create a 2nd repeatable quest with custom xp.
        quest = baker.make(Quest, xp=1, xp_can_be_entered_by_students=True, max_repeats=-1, max_xp=3)
        # submission with a custom XP values
        baker.make(QuestSubmission, quest=quest, user=self.student, semester=self.active_semester, is_approved=True, xp_requested=1)
        baker.make(QuestSubmission, quest=quest, user=self.student, semester=self.active_semester, is_approved=True, xp_requested=5)

        # despite 1 + 5, should only add 3 xp since max_xp is 3 for this repeatable quest
        xp = QuestSubmission.objects.calculate_xp(self.student)
        self.assertEqual(xp, 30)

    def test_calculate_xp__with_deleted_quest(self):
        """This method shouldn't break if a submission's quest has been deleted
        """
        # Give student 10 XP
        baker.make(QuestSubmission, user=self.student, quest__xp=10, semester=self.active_semester, is_approved=True)

        # Another quest that we'll delete
        quest_5xp = baker.make(Quest, max_xp=15, xp=5, max_repeats=-1)
        baker.make(
            QuestSubmission, user=self.student, quest=quest_5xp,
            semester=self.active_semester, is_approved=True
        )

        self.assertEqual(QuestSubmission.objects.calculate_xp(self.student), 15)

        # now delete the quest (submission is still there though!) Shouldn't break!
        quest_5xp.delete()
        self.assertEqual(QuestSubmission.objects.calculate_xp(self.student), 10)

        # Create a repeatable quest with custom xp.
        quest_5xp_custom = baker.make(Quest, xp=5, xp_can_be_entered_by_students=True, max_repeats=-1, max_xp=17)
        # submission with a custom XP values
        baker.make(QuestSubmission, quest=quest_5xp_custom, user=self.student, semester=self.active_semester, is_approved=True, xp_requested=8)
        self.assertEqual(QuestSubmission.objects.calculate_xp(self.student), 18)

        # now delete the custom_xp quest (submission is still there though!) Shouldn't break!
        quest_5xp_custom.delete()
        self.assertEqual(QuestSubmission.objects.calculate_xp(self.student), 10)
