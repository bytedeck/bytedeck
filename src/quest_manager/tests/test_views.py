from django.contrib.auth import get_user_model
from django.urls import reverse
from mock import patch
from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


class QuestViewQuickTests(ViewTestUtilsMixin, TenantTestCase):

    # includes some basic model data
    # fixtures = ['initial_data.json']

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.sem = SiteConfig.get().active_semester

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = baker.make(User)

        self.quest1 = baker.make(Quest)
        self.quest2 = baker.make(Quest)

        # self.sub1 = baker.make(QuestSubmission, user=self.test_student1, quest=self.quest1)
        # self.sub2 = baker.make(QuestSubmission, quest=self.quest1)

    def test_all_quest_page_status_codes_for_anonymous(self):
        """ If not logged in then all views should redirect to home page  """

        self.assertRedirectsLogin('quests:quests')

    def test_all_quest_page_status_codes_for_students(self):
        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        q_pk = self.quest1.pk
        q2_pk = self.quest2.pk

        self.assertEqual(self.client.get(reverse('quests:quests')).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:available')).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:available2')).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:inprogress')).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:completed')).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:past')).status_code, 200)
        # anyone can view drafts if they figure out the url, but it will be blank for them
        self.assertEqual(self.client.get(reverse('quests:drafts')).status_code, 200)

        self.assertEqual(self.client.get(reverse('quests:quest_detail', args=[q_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:quest_detail', args=[q_pk])).status_code, 200)

        #  students shouldn't have access to these and should be redirected to login
        self.assertEqual(self.client.get(reverse('quests:submitted')).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:submitted_all')).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:returned')).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:approved')).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:skipped')).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:submitted_for_quest', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:returned_for_quest', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:approved_for_quest', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:approved_for_quest_all', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:skipped_for_quest', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:quest_create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('quests:quest_update', args=[q_pk])).status_code, 403)

        self.assertEqual(self.client.get(reverse('quests:quest_copy', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:quest_delete', args=[q_pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('quests:start', args=[q2_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:hide', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:unhide', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:skip_for_quest', args=[q_pk])).status_code, 404)

    def test_all_quest_page_status_codes_for_teachers(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        s_pk = self.test_student1.profile.pk
        # s2_pk = self.test_student2.pk

        q_pk = self.quest1.pk
        q2_pk = self.quest2.pk

        self.assertEqual(self.client.get(reverse('profiles:profile_detail', args=[s_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('profiles:profile_update', args=[s_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('profiles:profile_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('profiles:profile_list_current')).status_code, 200)
        self.assertEqual(self.client.get(reverse('profiles:comment_ban', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:comment_ban_toggle', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:GameLab_toggle', args=[s_pk])).status_code, 302)
        # self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)

        self.assertEqual(self.client.get(reverse('quests:quest_delete', args=[q2_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:quest_copy', args=[q_pk])).status_code, 200)
    #
    # def test_profile_recalculate_xp_status_codes(self):
    #     """Need to test this view with students in an active course"""
    #     sem = baker.make(Semester)
    #     # since there's only one semester, it should be by default the active_semester (pk=1)
    #     self.assertEqual(sem.pk, djconfig.config.hs_active_semester)
    #     self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)

    def test_start(self):
        # log in a student from setUp
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        # if the quest is unavailable to the student, then should get a 404 if there is no submission started yet
        # but we don't care about implementation of `is_available()` here, so just patch it to return False
        with patch('quest_manager.models.Quest.is_available', return_value=False):
            response = self.client.get(reverse('quests:start', args=[self.quest1.pk]))
            self.assertEqual(response.status_code, 404)

        # if the quest has not been started yet, and it's available to the student, 
        # (quests created with default settings should be to students, as long as they are registered in a course)
        # then should redirect to the new submission that this view creates
        response = self.client.get(reverse('quests:start', args=[self.quest1.pk]))

        # check that a submission was created (should only be one at this point, so use `get()`
        sub = self.quest1.questsubmission_set.get(user=self.test_student1)
        # the view's response should redirect to the new submission's page
        self.assertRedirects(response, sub.get_absolute_url())       

        # try it again
        response = self.client.get(reverse('quests:start', args=[self.quest1.pk]))
        # this time shouldn't work because there is already submission in progress for this quest!
        # check that there is still one (and that another wasn't created)
        self.assertEqual(self.quest1.questsubmission_set.count(), 1)
        # the view should have redirect to the same submission:
        self.assertRedirects(response, sub.get_absolute_url()) 


class SubmissionViewTests(TenantTestCase):

    # includes some basic model data
    # fixtures = ['initial_data.json']

    def setUp(self):
        self.client = TenantClient(self.tenant)
        User = get_user_model()

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = baker.make(User)

        self.quest1 = baker.make(Quest)
        self.quest2 = baker.make(Quest)
        self.quest3 = baker.make(Quest, visible_to_students=False)

        self.sub1 = baker.make(QuestSubmission, user=self.test_student1, quest=self.quest1)
        self.sub2 = baker.make(QuestSubmission, quest=self.quest1)
        self.sub3 = baker.make(QuestSubmission, quest=self.quest2)
        self.sub4 = baker.make(
            QuestSubmission,
            user=self.test_student1,
            quest=self.quest3,
            is_completed=True,
            semester=SiteConfig.get().active_semester
        )

    def test_all_submission_page_status_codes_for_students(self):
        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        s1_pk = self.sub1.pk
        s2_pk = self.sub2.pk

        # Student's own submission
        self.assertEqual(self.client.get(reverse('quests:submission', args=[s1_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:drop', args=[s1_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:submission_past', args=[s1_pk])).status_code, 200)

        # Students shouldn't have access to these
        self.assertEqual(self.client.get(reverse('quests:flagged')).status_code, 302)

        # Student's own submission
        self.assertEqual(self.client.get(reverse('quests:skip', args=[s1_pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:approve', args=[s1_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:submission_past', args=[s1_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:flag', args=[s1_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:unflag', args=[s1_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:complete', args=[s1_pk])).status_code, 404)

        # Not this student's submission
        self.assertEqual(self.client.get(reverse('quests:submission', args=[s2_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:drop', args=[s2_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:skip', args=[s2_pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:submission_past', args=[s2_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:complete', args=[s2_pk])).status_code, 404)

        # Non existent submissions
        self.assertEqual(self.client.get(reverse('quests:submission', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:drop', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:skip', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:submission_past', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:complete', args=[0])).status_code, 404)

        # These Needs to be completed via POST
        self.assertEqual(self.client.get(reverse('quests:complete', args=[s1_pk])).status_code, 404)

    def test_student_can_view_completed_submission_when_hidden(self):
        """
        Make sure user can view quest even when visible_to_students is False
        and a student has a submission to it.
        """
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        s4_pk = self.sub4.pk

        response = self.client.get(reverse('quests:submission', args=[s4_pk]))
        self.assertEqual(response.status_code, 200)

    def test_student_can_drop_completed_submission_when_hidden(self):
        """
        Make sure student can drop a submission from a quest when an admin decides
        to hide it.
        """

        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        s4_pk = self.sub4.pk

        response = self.client.get(reverse('quests:drop', args=[s4_pk]))
        self.assertEqual(response.status_code, 200)

    def test_hidden_submission_does_not_contain_submit_button(self):
        """
        Make sure that submit for completion button is hidden since it's not available
        for students to submit anymore.
        """
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        s4_pk = self.sub4.pk

        response = self.client.get(reverse('quests:submission', args=[s4_pk]))
        self.assertNotContains(response, 'Submit Quest for Completion')

    def test_drop_button_not_visible_when_submission_approved(self):
        """
        Make sure drop button is not visible when quest submission is already approved
        """
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        self.sub4.is_approved = True
        self.sub4.save()
        s4_pk = self.sub4.pk

        response = self.client.get(reverse('quests:submission', args=[s4_pk]))
        self.assertNotContains(response, 'Drop Quest')

    def test_drop_approved_submission_results_to_404(self):
        """
        Make sure a student cannot drop an approved submission
        """
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        self.sub4.is_approved = True
        self.sub4.save()
        s4_pk = self.sub4.pk

        response = self.client.get(reverse('quests:drop', args=[s4_pk]))
        self.assertEqual(response.status_code, 404)

    def test_all_submission_page_status_codes_for_teachers(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        s1_pk = self.sub1.pk
        # s2_pk = self.sub2.pk

        self.assertEqual(self.client.get(reverse('quests:flagged')).status_code, 200)

        # View it
        self.assertEqual(self.client.get(reverse('quests:submission', args=[s1_pk])).status_code, 200)
        # Flag it
        # self.assertEqual(self.client.get(reverse('quests:flag', args=[s1_pk])).status_code, 200)
        self.assertRedirects(
            response=self.client.get(reverse('quests:flag', args=[s1_pk])),
            expected_url=reverse('quests:approvals'),
        )
        # TODO Why does this fail? Why is self.sub1.flagged_by == None
        # self.assertEqual(self.sub1.flagged_by, self.test_teacher)

        # Unflag it
        self.assertRedirects(
            response=self.client.get(reverse('quests:unflag', args=[s1_pk])),
            expected_url=reverse('quests:approvals'),
        )
        self.assertIsNone(self.sub1.flagged_by)

        # self.assertEqual(self.client.get(reverse('quests:drop', args=[s1_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:submission_past', args=[s1_pk])).status_code, 200)

        # Non existent submissions
        self.assertEqual(self.client.get(reverse('quests:submission', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:drop', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:skip', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:submission_past', args=[0])).status_code, 404)

        # These Needs to be completed via POST
        # self.assertEqual(self.client.get(reverse('quests:complete', args=[s1_pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:skip', args=[s1_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:approve', args=[s1_pk])).status_code, 404)

    def test_student_quest_completion(self):
        # self.sub1 = baker.make(QuestSubmission, user=self.test_student1, quest=self.quest1)

        # self.assertRedirects(
        #     response=self.client.post(reverse('quests:complete', args=[self.sub1.id])),
        #     expected_url=reverse('quests:quests'),
        # )

        # TODO self.assertEqual(self.client.get(reverse('quests:complete', args=[s1_pk])).status_code, 404)
        pass

    def test_submission_when_quest_not_visible(self):
        """When a quest is hidden from students, they should still be able to to see their submission in a static way"""
        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        # Make quest invisible to students
        self.quest1.visible_to_students = False
        self.quest1.save()
        self.assertFalse(self.quest1.visible_to_students)

        # TODO: should redirect, not 404?
        self.assertEqual(self.client.get(reverse('quests:submission', args=[self.sub1.pk])).status_code, 404)

    def test_ajax_save_draft(self):
        # loging required for this view
        self.client.force_login(self.test_student1)
        quest = baker.make(Quest, name="TestSaveDrafts")
        sub = baker.make(QuestSubmission, quest=quest)
        draft_comment = "Test draft comment"
        # Send some draft data via the ajax view, which should save it.
        ajax_data = {
            'comment': draft_comment,
            'submission_id': sub.id,
        }

        response = self.client.post(
            reverse('quests:ajax_save_draft'),
            data=ajax_data,
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['result'], "Draft saved")

        sub.refresh_from_db()
        self.assertEqual(draft_comment, sub.draft_text)  # fAILS CUS MODEL DIDN'T SAVE! aRGH..


class QuestCreateAndDeleteViewTest(ViewTestUtilsMixin, TenantTestCase):
    """ Unit Tests for:

        class QuestCreate(AllowNonPublicViewMixin, UserPassesTestMixin, CreateView)
        class QuestDelete(AllowNonPublicViewMixin, UserPassesTestMixin, DeleteView)
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_teacher = User.objects.create_user('test_teacher', password="password", is_staff=True)
        self.test_student = User.objects.create_user('test_student', password="password")

    def test_teacher(self):
        # simulate a logged in teacher
        self.client.force_login(self.test_teacher)

        # get some default form data
        response = self.client.get(reverse('quests:quest_create'))
        self.assertEqual(response.status_code, 200)

        new_test_name = "Test Quest Creation"
        form_data = {
            'name': new_test_name,  # only blank required field
            # these fields are required but they have defaults
            'xp': 0,
            'max_repeats': 0,
            'hours_between_repeats': 0, 
            'sort_order': 0,
            'date_available': "2006-10-25",
            'time_available': "14:30:59",
        }

        response = self.client.post(
            reverse('quests:quest_create'),
            data=form_data
        )

        # Get the newest Quest
        new_quest = Quest.objects.latest('datetime_created')
        self.assertEqual(new_quest.name, new_test_name)
        # if successful, should redirect to the new quest
        self.assertRedirects(
            response, 
            new_quest.get_absolute_url()
        )

        # now let's delete
        response = self.client.post(
            reverse('quests:quest_delete', args=[new_quest.id]),
        )
        self.assertRedirects(response, reverse('quests:quests'))

        # shouldn't exist anymore now that we deleted it!
        with self.assertRaises(Quest.DoesNotExist):
            Quest.objects.get(id=new_quest.id)

    def test_TA_can_create_draft_quests_and_delete_own(self):
        # simulate a logged in TA (teaching assistant = a student with extra permissions)
        test_ta = User.objects.create_user('test_ta')
        test_ta.profile.is_TA = True  # profiles are create automatically via User post_save signal
        test_ta.profile.save()
        self.client.force_login(test_ta)

        # Can access the Create view
        response = self.client.get(reverse('quests:quest_create'))
        self.assertEqual(response.status_code, 200)

        # Post the form view to create a new quest

        # Confirm the quest is a draft

        # They can delete their own quest

        # But they can't delete other quests

        # new_test_name = "Test Quest Creation"
        # form_data = {
        #     'name': new_test_name,  # only blank required field
        #     # these fields are required but they have defaults
        #     'xp': 0,
        #     'max_repeats': 0,
        #     'hours_between_repeats': 0, 
        #     'sort_order': 0,
        #     'date_available': "2006-10-25",
        #     'time_available': "14:30:59",
        # }

        # response = self.client.post(
        #     reverse('quests:quest_create'),
        #     data=form_data
        # )

        # # Get the newest Quest
        # new_quest = Quest.objects.latest('datetime_created')
        # self.assertEqual(new_quest.name, new_test_name)
        # # if successful, should redirect to the new quest
        # self.assertRedirects(
        #     response, 
        #     new_quest.get_absolute_url()
        # )

        # # now let's delete
        # response = self.client.post(
        #     reverse('quests:quest_delete', args=[new_quest.id]),
        # )
        # self.assertRedirects(response, reverse('quests:quests'))

        # # shouldn't exist anymore now that we deleted it!
        # with self.assertRaises(Quest.DoesNotExist):
        #     Quest.objects.get(id=new_quest.id)
