from mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse

from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from siteconfig.models import SiteConfig

from quest_manager.models import QuestSubmission, Quest


class QuestViewTests(TenantTestCase):

    # includes some basic model data
    # fixtures = ['initial_data.json']

    def setUp(self):
        self.client = TenantClient(self.tenant)
        User = get_user_model()
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

        self.assertRedirects(
            response=self.client.get(reverse('quests:quests')),
            expected_url='%s?next=%s' % (reverse('home'), reverse('quests:quests')),
        )

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
        self.sem = SiteConfig.get().active_semester

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = baker.make(User)

        self.quest1 = baker.make(Quest)
        self.quest2 = baker.make(Quest)

        self.sub1 = baker.make(QuestSubmission, user=self.test_student1, quest=self.quest1)
        self.sub2 = baker.make(QuestSubmission, quest=self.quest1)
        self.sub3 = baker.make(QuestSubmission, quest=self.quest2)

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

        # Non existent submissions
        self.assertEqual(self.client.get(reverse('quests:submission', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:drop', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:skip', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:submission_past', args=[0])).status_code, 404)
        self.assertEqual(self.client.get(reverse('quests:complete', args=[0])).status_code, 404)

        # These Needs to be completed via POST
        self.assertEqual(self.client.get(reverse('quests:complete', args=[s1_pk])).status_code, 404)

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

        # Should be able to see own submission even when quest is closed
        self.assertEqual(self.client.get(reverse('quests:submission', args=[self.sub1.pk])).status_code, 200)


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
