"""
TEST ORGANIZATION

Each function/class-based-view has its own test class.

Within each test class, each use-case of the view has its own test method

The quick tests at the beginning can probably be removed once the full test suit is created,
or they could be moved into a `test_urls.py` module.

"""

from django.contrib.auth import get_user_model
from django.urls import reverse

from mock import patch
from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from notifications.models import Notification
from quest_manager.models import Category, Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


def create_two_test_files():
    """ returns a list of files for testing form views """
    # give it a unique name for easier testing, otherwise when re-testing,
    # the name will be appended with stuff because the file already exists
    import uuid

    from django.core.files.uploadedfile import SimpleUploadedFile
    test_filename1 = str(uuid.uuid1().hex) + ".txt"
    test_file1 = SimpleUploadedFile(test_filename1, b"file_content1", 'text/plain')
    test_filename2 = str(uuid.uuid1().hex) + ".txt"
    test_file2 = SimpleUploadedFile(test_filename2, b"file_content2", 'text/plain')

    return [test_file1, test_file2]


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
        self.assertEqual(self.client.get(reverse('quests:flagged')).status_code, 302)
        # self.assertEqual(self.client.get(reverse('quests:skipped')).status_code, 302)
        # self.assertEqual(self.client.get(reverse('quests:submitted_for_quest', args=[q_pk])).status_code, 302)
        # self.assertEqual(self.client.get(reverse('quests:returned_for_quest', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:approved_for_quest', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:approved_for_quest_all', args=[q_pk])).status_code, 302)
        # self.assertEqual(self.client.get(reverse('quests:skipped_for_quest', args=[q_pk])).status_code, 302)

        self.assertEqual(self.client.get(reverse('quests:start', args=[q2_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:hide', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:unhide', args=[q_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('quests:skip_for_quest', args=[q_pk])).status_code, 404)

        # 403 for CRUD views:
        self.assertEqual(self.client.get(reverse('quests:quest_create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('quests:quest_update', args=[q_pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('quests:quest_copy', args=[q_pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('quests:quest_delete', args=[q_pk])).status_code, 403)

    def test_all_quest_page_status_codes_for_teachers(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        q_pk = self.quest1.pk
        q2_pk = self.quest2.pk

        self.assertEqual(self.client.get(reverse('quests:quest_delete', args=[q2_pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('quests:quest_copy', args=[q_pk])).status_code, 200)

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

    def test_ajax_save_draft_has_changes(self):
        """Should save if there are changes in the draft text"""
        # loging required for this view
        self.client.force_login(self.test_student1)
        quest = baker.make(Quest, name="TestSaveDrafts")
        sub = baker.make(QuestSubmission,
                         quest=quest,
                         draft_text="I am a test draft comment")
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

    def test_ajax_save_draft_no_changes(self):
        """Should not save if there are no changes in the draft text"""
        # loging required for this view
        self.client.force_login(self.test_student1)
        quest = baker.make(Quest, name="TestSaveDrafts")
        sub = baker.make(QuestSubmission,
                         quest=quest,
                         draft_text="I am a test draft comment")
        draft_comment = "I am a test draft comment"
        # Send the same draft data via the ajax view, which should not save it
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
        self.assertEqual(response.json()['result'], "No changes")

        sub.refresh_from_db()
        self.assertEqual(draft_comment, sub.draft_text)


class SubmissionCompleteViewTest(ViewTestUtilsMixin, TenantTestCase):
    """ Tests for view.py :

        def complete(request, submission_id)

        via urls.py

        url(r'^submission/(?P<submission_id>[0-9]+)/complete/$', views.complete, name='complete'),

    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_teacher = User.objects.create_user('test_teacher', password="password", is_staff=True)
        self.test_student = User.objects.create_user('test_student', password="password")

        # log in the student for all tests here
        self.client.force_login(self.test_student)

        self.quest = baker.make(Quest, xp=5)
        self.quest_repeatable_with_max_xp = baker.make(Quest, max_xp=15, xp=5, max_repeats=-1)
        self.sub = baker.make(QuestSubmission, user=self.test_student, quest=self.quest)

    def post_complete(self, button='complete', submission_comment="test comment", teachers_list=None):
        """ Convenience method for posting the complete() view.
        If teachers_list is not provided, [self.test_teacher] is used.
        """
        if not teachers_list:
            teachers_list = [self.test_teacher]
        with patch('profile_manager.models.Profile.current_teachers', return_value=teachers_list):
            response = self.client.post(
                reverse('quests:complete', args=[self.sub.id]),
                data={'comment_text': submission_comment, button: True}
            )
        return response

    def test_complete(self):
        """ Students can complete quests that are available to them.  Form is submitted with the 'complete' button
        Are redirected to their available quests page, submission is marked completed and has a completion time
        """
        comment = "test submission comment"
        response = self.post_complete(submission_comment=comment)
        self.assertRedirects(response, expected_url=reverse('quests:quests'))
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.is_completed)

        self.assertSuccessMessage(response)

        # make sure the comment was created
        comments = self.sub.get_comments()
        self.assertEqual(comments.count(), 1)
        self.assertEqual(comments[0].text, comment)

    def test_complete_more_submissions_no_additional_xp(self):
        """
        Student can complete quests that are availabe to them multiple times but they cannot earn xp more than the max_xp
        that can be gained in a repeatable quest
        """
        semester = SiteConfig.get().active_semester
        baker.make(QuestSubmission, user=self.test_student, quest=self.quest_repeatable_with_max_xp, semester=semester, is_approved=True)
        baker.make(QuestSubmission, user=self.test_student, quest=self.quest_repeatable_with_max_xp, semester=semester, is_approved=True)
        baker.make(QuestSubmission, user=self.test_student, quest=self.quest_repeatable_with_max_xp, semester=semester, is_approved=True)

        self.assertEqual(QuestSubmission.objects.calculate_xp(self.test_student), 15)

        # Perform additional submission but xp remains the same
        baker.make(QuestSubmission, user=self.test_student, quest=self.quest_repeatable_with_max_xp, semester=semester, is_approved=True)
        self.assertEqual(QuestSubmission.objects.calculate_xp(self.test_student), 15)

    def test_no_comment_verification_not_required(self):
        """ When a quest is automatically approved, it does not require a comment
        """
        self.sub.quest.verification_required = False
        self.sub.quest.save()

        response = self.post_complete(submission_comment="")
        self.assertRedirects(response, expected_url=reverse('quests:quests'))
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.is_completed)

        self.assertSuccessMessage(response)

    def test_no_comment_but_verification_required(self):
        """ When a quest requires teacher's approval, it means they must include either files or a comment
        """
        self.sub.quest.verification_required = True
        self.sub.quest.save()

        response = self.post_complete(submission_comment="")

        # Should redirect back to the submission with error message
        self.assertRedirects(response, expected_url=self.sub.get_absolute_url())
        self.sub.refresh_from_db()
        self.assertFalse(self.sub.is_completed)

        self.assertErrorMessage(response)

    def test_quest_not_available(self):
        """ If a quest is not available to a student, they should not be able to complete it """
        # TODO
        # # Easy way to make unavailable, should probably patch the available quests lists instead though...
        # self.quest.visibel_to_student = False
        # self.quest.save()

        # response = self.post_complete(comment="")
        # # Should redirect back to the submission with error message
        # self.assertEqual(response.status_code, 404)
        pass

    def test_notifications_own_student(self):
        """ Teacher should NOT be notified when their student complete's a quest, because it
        will appear in there approvals tab anyway, so redundant
        """
        self.sub.quest.verification_required = True  # default anyway, but make it explicit
        self.sub.quest.save()

        self.post_complete()

        notifications = Notification.objects.all_for_user_target(self.test_teacher, self.sub)
        self.assertEqual(notifications.count(), 0)

    def test_notifications_comment_when_verification_not_required(self):
        """ Teacher SHOULD be notified when their student complete's a quest if:
        1. it has a comment, AND
        2. it does not require verification
        Otherwise teacher would not notice the comment
        """
        self.sub.quest.verification_required = False
        self.sub.quest.save()

        self.post_complete()

        notifications = Notification.objects.all_for_user_target(self.test_teacher, self.sub)
        self.assertEqual(notifications.count(), 1)

    def test_notifications_no_comment_when_verification_not_required(self):
        """ Teacher should NOT be notified when there is no comment and it's auto-approved (verification_required=False):
        """
        self.sub.quest.verification_required = False
        self.sub.quest.save()

        self.post_complete(submission_comment="")

        notifications = Notification.objects.all_for_user_target(self.test_teacher, self.sub)
        self.assertEqual(notifications.count(), 0)

    def test_specific_teacher_to_notify_own_teacher(self):
        """ If a quest has a specific teacher linked to it, they should be notified of completions if
        the student is not in one of that teacher's courses (if they are in the teacher's course, then the submission will
        appear in their "Approvals" tab anyway and notification is redundant)
        """
        self.sub.quest.specific_teacher_to_notify = self.test_teacher
        self.sub.quest.save()

        self.post_complete(teachers_list=[self.test_teacher])  # test_teacher is default but be explicit

        notifications = Notification.objects.all_for_user_target(self.test_teacher, self.sub)
        self.assertEqual(notifications.count(), 0)

    def test_specific_teacher_to_notify_other_teacher(self):
        """ If a quest has a specific teacher linked to it, they should be notified of completions if
        the student is not in one of that teacher's courses (if they are in the teacher's course, then the submission will
        appear in their "Approvals" tab anyway and notification is redundant)
        """
        special_teacher = User.objects.create_user('special_teacher', password="password", is_staff=True)
        self.sub.quest.specific_teacher_to_notify = special_teacher
        self.sub.quest.save()

        self.post_complete(teachers_list=[self.test_teacher])  # test_teacher is default but be explicit

        notifications = Notification.objects.all_for_user_target(special_teacher, self.sub)
        self.assertEqual(notifications.count(), 1)

        # and still no notification needed for actual teacher of student:
        notifications = Notification.objects.all_for_user_target(self.test_teacher, self.sub)
        self.assertEqual(notifications.count(), 0)

    def test_comment_completed(self):
        """ Students can comment on already completed quests.
        """
        comment = "test submission comment"
        response = self.post_complete(button="comment", submission_comment=comment)
        self.assertRedirects(response, expected_url=reverse('quests:quests'))

        self.assertSuccessMessage(response)
        # make sure the comment was created
        comments = self.sub.get_comments()
        self.assertEqual(comments.count(), 1)
        self.assertEqual(comments[0].text, comment)

    def test_comment_button_no_comment_verification_not_required(self):
        """ When commenting on an already completed quest, needs to actually comment with something
        whether or not verification was required originally
        """
        self.sub.quest.verification_required = False
        self.sub.quest.save()

        response = self.post_complete(button="comment", submission_comment="")
        # Should redirect back to the submission with error message
        self.assertRedirects(response, expected_url=self.sub.get_absolute_url())
        self.assertErrorMessage(response)

    def test_comment_button_no_comment_but_verification_required(self):
        """ When commenting on an already completed quest, needs to actually comment with something
        whether or not verification was required originally
        """
        self.sub.quest.verification_required = True
        self.sub.quest.save()

        response = self.post_complete(button="comment", submission_comment="")

        # Should redirect back to the submission with error message
        self.assertRedirects(response, expected_url=self.sub.get_absolute_url())
        self.sub.refresh_from_db()
        self.assertFalse(self.sub.is_completed)

        self.assertErrorMessage(response)

    # def test_quest_not_available(self):
    #     """ If a quest is not available to a student, they should not be able to complete it """
    #     # TODO
    #     # # Easy way to make unavailable, should probably patch the available quests lists instead though...
    #     # self.quest.visibel_to_student = False
    #     # self.quest.save()

    #     # response = self.post_complete(button="comment", comment="")
    #     # # Should redirect back to the submission with error message
    #     # self.assertEqual(response.status_code, 404)
    #     pass

    def test_comment_button_notifications_own_student(self):
        """ Teacher should be notified when their student comments on an already complete's a quest
        """
        self.sub.quest.verification_required = True  # default anyway, but make it explicit
        self.sub.quest.save()

        self.post_complete(button="comment")
        notifications = Notification.objects.all_for_user_target(self.test_teacher, self.sub)
        self.assertEqual(notifications.count(), 1)

    def test_comment_button__notifications_comment_when_verification_not_required(self):
        """ Teacher SHOULD always be notified on comments on already completed quests,
        even if verification was not required originally
        """
        self.sub.quest.verification_required = False
        self.sub.quest.save()

        self.post_complete(button="comment")

        notifications = Notification.objects.all_for_user_target(self.test_teacher, self.sub)
        self.assertEqual(notifications.count(), 1)

    def test_comment_button_specific_teacher_to_notify_own_teacher(self):
        """ If comment is left on an already completed quest that has a specific teacher linked to it,
        both of them should be notified of the comment (the specific teacher, and the normal teacher)

        In this case, they are the same teacher, so don't send two notifications!
        """
        self.sub.quest.specific_teacher_to_notify = self.test_teacher
        self.sub.quest.save()

        self.post_complete(button="comment", teachers_list=[self.test_teacher])  # test_teacher is default but be explicit

        notifications = Notification.objects.all_for_user_target(self.test_teacher, self.sub)
        self.assertEqual(notifications.count(), 1)

    def test_comment_button_specific_teacher_to_notify_other_teacher(self):
        """ If comment is left on an already completed quest that has a specific teacher linked to it,
        both of them should be notified of the comment (the specific teacher, and the normal teacher)
        """
        special_teacher = User.objects.create_user('special_teacher', password="password", is_staff=True)
        self.sub.quest.specific_teacher_to_notify = special_teacher
        self.sub.quest.save()

        self.post_complete(button="comment", teachers_list=[self.test_teacher])  # test_teacher is default but be explicit

        notifications = Notification.objects.all_for_user_target(special_teacher, self.sub)
        self.assertEqual(notifications.count(), 1)

        # and notify actual teacher of student:
        notifications = Notification.objects.all_for_user_target(self.test_teacher, self.sub)
        self.assertEqual(notifications.count(), 1)

    def test_notification_when_teacher_comments(self):
        """ When a teacher comments on submission and student gets notified
        """
        # log in a teacher to comment on the submission
        self.client.force_login(self.test_teacher)
        self.post_complete(button="comment")

        # Teacher shouldn't get a nofication if they are the ones leaving a comment
        notifications = Notification.objects.all_for_user_target(self.test_teacher, self.sub)
        self.assertEqual(notifications.count(), 0)

        # Student is notified
        notifications = Notification.objects.all_for_user_target(self.test_student, self.sub)
        self.assertEqual(notifications.count(), 1)

    def test_comment_button_files_in_form(self):
        """ Files can be uploaded and attached to comments when completing or commenting on quests
        and a link to the file is included in the comment.
        """
        test_files = create_two_test_files()
        with patch('profile_manager.models.Profile.current_teachers', return_value=[self.test_teacher]):
            response = self.client.post(
                reverse('quests:complete', args=[self.sub.id]),
                data={'comment': True, 'attachments': test_files}
            )

        self.assertRedirects(response, expected_url=reverse('quests:quests'))

        # make sure the files exist
        from comments.models import Comment
        comment = Comment.objects.all_with_target_object(self.sub).first()
        self.assertTrue(comment)  # not empty or None etc
        comment_files_qs = comment.document_set.all()
        self.assertEqual(comment_files_qs.count(), 2)

        # make sure they are the correct
        comment_files = list(comment_files_qs)  # evalute qs so we can slice without weirdness
        import os
        self.assertEqual(os.path.basename(comment_files[0].docfile.name), test_files[0].name)
        self.assertEqual(os.path.basename(comment_files[1].docfile.name), test_files[1].name)

    def test_unrecognized_submit_button(self):
        """ Unrecognized form submit button should 404.
        In some views Summernote was causing problems by submitting the form via ajax """
        response = self.post_complete(button="non_existant_button")
        self.assertEqual(response.status_code, 404)

    def test_invalid_submission_form(self):
        """ I don't think thie form CAN be invalid... how? None of the fields are required. """
        # with patch('profile_manager.models.Profile.current_teachers', return_value=self.test_teacher):
        #     response = self.client.post(
        #         reverse('quests:complete', args=[self.sub.id]),
        #         data={}
        #     )
        # # bad form, just rerender
        # self.assertEqual(response.status_code, 200)
        pass


class QuestCRUDViewsTest(ViewTestUtilsMixin, TenantTestCase):
    """ Tests for:

        class QuestCreate(NonPublicOnlyViewMixin, UserPassesTestMixin, CreateView)
        class QuestDelete(NonPublicOnlyViewMixin, UserPassesTestMixin, DeleteView)
        class QuestUpdate(NonPublicOnlyViewMixin, UserPassesTestMixin, UpdateView)
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_teacher = User.objects.create_user('test_teacher', password="password", is_staff=True)
        self.test_student = User.objects.create_user('test_student', password="password")

        self.minimal_valid_form_data = {
            'name': "Test Quest",  # only blank required field
            # these fields are required but they have defaults
            'xp': 0,
            'max_repeats': 0,
            'max_xp': -1,
            'hours_between_repeats': 0,
            'sort_order': 0,
            'date_available': "2006-10-25",
            'time_available': "14:30:59",
        }

    def test_teacher_can_create_and_delete_quests(self):
        # simulate a logged in teacher
        self.client.force_login(self.test_teacher)

        # Can access the Create view
        self.assert200('quests:quest_create')

        response = self.client.post(
            reverse('quests:quest_create'),
            data=self.minimal_valid_form_data
        )

        # Get the newest Quest
        new_quest = Quest.objects.latest('datetime_created')
        self.assertEqual(new_quest.name, "Test Quest")
        # if successful, should redirect to the new quest
        self.assertRedirects(response, new_quest.get_absolute_url())

        # now let's delete
        response = self.client.post(reverse('quests:quest_delete', args=[new_quest.id]))
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
        self.assert200('quests:quest_create')

        # Post the form view to create a new quest
        response = self.client.post(reverse('quests:quest_create'), data=self.minimal_valid_form_data)

        # Confirm Quest object was created
        new_quest = Quest.objects.latest('datetime_created')
        self.assertEqual(new_quest.name, "Test Quest")

        # Should redirect to the new quest:
        self.assertRedirects(response, new_quest.get_absolute_url())

        # Confirm the quest is a draft and not visible to students
        self.assertFalse(new_quest.visible_to_students)
        # also they should be the quest's editor
        self.assertEqual(new_quest.editor, test_ta)

        # They can delete their own quests
        response = self.client.post(reverse('quests:quest_delete', args=[new_quest.id]))
        self.assertRedirects(response, reverse('quests:quests'))

        # shouldn't exist anymore now that we deleted it!
        with self.assertRaises(Quest.DoesNotExist):
            Quest.objects.get(id=new_quest.id)

        # But they can't delete other quests, permission denied
        other_quest = baker.make(Quest)
        response = self.client.post(reverse('quests:quest_delete', args=[other_quest.id]))
        self.assertEqual(response.status_code, 403)

    def test_teacher_can_update_quests(self):
        # simulate a logged in teacher
        self.client.force_login(self.test_teacher)

        # make a quest for us to update, use the form data so easier to track what we're updating
        # and so we have access to all the other fields we need to post
        quest_to_update = Quest.objects.create(**self.minimal_valid_form_data)

        # Can't access Update view for a quest in which they aren't the editor
        self.assert200('quests:quest_update', kwargs={'pk': quest_to_update.pk})

        # Change the name of the quest, in the form data
        updated_quest_data = self.minimal_valid_form_data
        updated_quest_data['name'] = "Updated Name"

        # Can post form and save updates
        response = self.client.post(
            reverse('quests:quest_update', kwargs={'pk': quest_to_update.pk}),
            data=updated_quest_data
        )

        # Should redirect to the edited quest:
        self.assertRedirects(response, quest_to_update.get_absolute_url())

        # Confrim quest was updated
        quest_to_update.refresh_from_db()
        self.assertEqual(quest_to_update.name, "Updated Name")

    def test_ta_can_update_their_own_quests(self):
        # simulate a logged in TA (teaching assistant = a student with extra permissions)
        test_ta = User.objects.create_user('test_ta')
        test_ta.profile.is_TA = True  # profiles are create automatically via User post_save signal
        test_ta.profile.save()
        self.client.force_login(test_ta)

        # make a quest for us to update, use the form data so easier to track what we're updating
        # and so we have access to all the other fields we need to post
        quest_to_update = Quest.objects.create(**self.minimal_valid_form_data)

        # Can't access Update view for a quest in which they aren't the editor
        self.assert403('quests:quest_update', kwargs={'pk': quest_to_update.pk})

        # make them the editor so they can update
        quest_to_update.editor = test_ta
        quest_to_update.save()

        # Still can't access Update view becuase the quest is visible_to_students
        # Don't want TA's editing "live" quests
        self.assert403('quests:quest_update', kwargs={'pk': quest_to_update.pk})

        quest_to_update.visible_to_students = False
        quest_to_update.save()

        self.assert200('quests:quest_update', kwargs={'pk': quest_to_update.pk})

        # Change the name of the quest, in the form data
        updated_quest_data = self.minimal_valid_form_data
        updated_quest_data['name'] = "Updated Name"

        # Can post form and save updates
        response = self.client.post(
            reverse('quests:quest_update', kwargs={'pk': quest_to_update.pk}),
            data=updated_quest_data
        )

        # Should redirect to the edited quest:
        self.assertRedirects(response, quest_to_update.get_absolute_url())

        # Confrim quest was updated
        quest_to_update.refresh_from_db()
        self.assertEqual(quest_to_update.name, "Updated Name")

    # TODO
    # TAs should not be able to make a quest visible_to_students
    # When a quest is made visible_to_students by a teacher, the editor should be removed

    def test_create_with_new_prereqs(self):
        """ Add a quest and badge prereq during quest creation """
        self.client.force_login(self.test_teacher)
        self.minimal_valid_form_data['new_quest_prerequisite'] = baker.make(Quest).id
        self.minimal_valid_form_data['new_badge_prerequisite'] = baker.make('badges.Badge').id
        response = self.client.post(reverse('quests:quest_create'), data=self.minimal_valid_form_data)
        new_quest = Quest.objects.latest('datetime_created')
        self.assertRedirects(response, new_quest.get_absolute_url())
        self.assertEqual(new_quest.prereqs().count(), 2)

    def test_update_with_new_prereqs(self):
        """ Add a quest and badge prereq during quest editing, also overwrite existing prereqs with new ones on update """
        self.client.force_login(self.test_teacher)
        quest_to_update = baker.make(Quest)
        self.assertEqual(quest_to_update.prereqs().count(), 0)

        self.minimal_valid_form_data['new_quest_prerequisite'] = baker.make(Quest, name="new-prereq-quest").id
        self.minimal_valid_form_data['new_badge_prerequisite'] = baker.make('badges.Badge', name="new-prereq-badge").id
        response = self.client.post(
            reverse('quests:quest_update', kwargs={'pk': quest_to_update.pk}),
            data=self.minimal_valid_form_data
        )
        self.assertRedirects(response, quest_to_update.get_absolute_url())
        self.assertEqual(quest_to_update.prereqs().count(), 2)
        self.assertIn("new-prereq-quest", str(quest_to_update.prereqs()))
        self.assertIn("new-prereq-badge", str(quest_to_update.prereqs()))

        # now update again, overwriting existing prereqs:
        self.minimal_valid_form_data['new_quest_prerequisite'] = baker.make(Quest, name="new-prereq-quest2").id
        self.minimal_valid_form_data['new_badge_prerequisite'] = ''

        response = self.client.post(
            reverse('quests:quest_update', kwargs={'pk': quest_to_update.pk}),
            data=self.minimal_valid_form_data
        )
        self.assertRedirects(response, quest_to_update.get_absolute_url())
        self.assertEqual(quest_to_update.prereqs().count(), 1)
        self.assertIn("new-prereq-quest2", str(quest_to_update.prereqs()))


class QuestCopyViewTest(ViewTestUtilsMixin, TenantTestCase):
    """ Tests for:

            def quest_copy(request, quest_id):

            via

            url(r'^(?P<quest_id>[0-9]+)/copy/$', views.quest_copy, name='quest_copy'),
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_student = User.objects.create_user('test_student', password="password")
        self.test_teacher = User.objects.create_user('test_teacher', password="password", is_staff=True)
        self.quest = baker.make(Quest, name="Test Quest")

        # simulate a logged in TA (teaching assistant = a student with extra permissions)
        self.test_ta = User.objects.create_user('test_ta')
        self.test_ta.profile.is_TA = True  # profiles are create automatically via User post_save signal
        self.test_ta.profile.save()

        self.valid_copy_form_data = {
            'name': "Test Quest - COPY",  # only blank required field
            # these fields are required but they have defaults
            'xp': 0,
            'max_repeats': 0,
            'max_xp': -1,
            'hours_between_repeats': 0,
            'sort_order': 0,
            'date_available': "2006-10-25",
            'time_available': "14:30:59",
            'new_quest_prerequisite': self.quest.id,
        }

    def test_teacher_copy_quest_GET(self):
        self.client.force_login(self.test_teacher)

        get_response = self.client.get(reverse('quests:quest_copy', args=[self.quest.id]))
        self.assertEqual(get_response.status_code, 200)

        # Get the data from the form  (initial visit to the page)
        form_data = get_response.context['form'].initial

        # Quest name should have changed
        self.assertEqual(form_data['name'], 'Test Quest - COPY')
        # And by default form should have prereq set
        self.assertEqual(form_data['new_quest_prerequisite'], self.quest)

    def test_teacher_copy_quest_POST(self):
        self.client.force_login(self.test_teacher)

        response = self.client.post(
            reverse('quests:quest_copy', args=[self.quest.id]),
            data=self.valid_copy_form_data,
        )

        # Check that the new copied quest exists:
        self.assertTrue(Quest.objects.filter(name='Test Quest - COPY').exists())
        new_quest = Quest.objects.get(name='Test Quest - COPY')
        # if successful, should redirect to the new quest
        self.assertRedirects(response, new_quest.get_absolute_url())

        # Copied quests should set the original as a pre-requisite
        self.assertEqual(new_quest.prereqs().count(), 1)
        self.assertEqual(new_quest.prereqs().first().prereq_object, self.quest)

    def test_TA_can_copy_quest_GET(self):

        self.client.force_login(self.test_ta)
        get_response = self.client.get(reverse('quests:quest_copy', args=[self.quest.id]))
        self.assertEqual(get_response.status_code, 200)

        # Get the data from the form  (initial visit to the page)
        form_data = get_response.context['form'].initial

        # Quest name should have changed
        self.assertEqual(form_data['name'], 'Test Quest - COPY')
        # And by default form should have prereq set
        self.assertEqual(form_data['new_quest_prerequisite'], self.quest)
        # self.assertFalse(form_data['visible_to_students']) ? When is this changed?

        # Also, TA's should not be able to set visible_to_students, but it is by default
        # just make sure it is visible, and then check again after form is posted

    def test_TA_copy_quest_POST(self):
        self.client.force_login(self.test_ta)
        response = self.client.post(
            reverse('quests:quest_copy', args=[self.quest.id]),
            data=self.valid_copy_form_data,
        )

        # Check that the new copied quest exists:
        self.assertTrue(Quest.objects.filter(name='Test Quest - COPY').exists())
        new_quest = Quest.objects.get(name='Test Quest - COPY')

        # For TAs only, quest should be forced to not visible to students
        self.assertFalse(new_quest.visible_to_students)
        # and the TA should have been set as the editor
        self.assertEqual(new_quest.editor, self.test_ta)

        # Same tests as for Teacher:
        # if successful, should redirect to the new quest
        self.assertRedirects(response, new_quest.get_absolute_url())

        # Copied quests should set the original as a pre-requisite
        self.assertEqual(new_quest.prereqs().count(), 1)
        self.assertEqual(new_quest.prereqs().first().prereq_object, self.quest)

    def test_copy_with_new_prereqs(self):
        """ When copying a quest should be able to set new prereqs """
        self.client.force_login(self.test_teacher)

        get_response = self.client.get(reverse('quests:quest_copy', args=[self.quest.id]))
        self.assertEqual(get_response.status_code, 200)

        # See above tests for explanation of this....(EXPLANATION REMOVED because above tests changed)
        form_data = get_response.context['form'].initial
        form_data = {k: "" if v is None else v for (k, v) in form_data.items()}
        form_data['icon'] = ""
        form_data['new_quest_prerequisite'] = baker.make(Quest, name="new-prereq-quest").id
        form_data['new_badge_prerequisite'] = baker.make('badges.Badge', name="new-prereq-badge").id

        response = self.client.post(
            reverse('quests:quest_copy', args=[self.quest.id]),
            data=form_data
        )
        copied_quest = Quest.objects.latest('datetime_created')
        self.assertRedirects(response, copied_quest.get_absolute_url())

        self.assertEqual(copied_quest.prereqs().count(), 2)
        self.assertIn("new-prereq-quest", str(copied_quest.prereqs()))
        self.assertIn("new-prereq-badge", str(copied_quest.prereqs()))


class QuestListViewTest(ViewTestUtilsMixin, TenantTestCase):
    """ Tests for:

        def quest_list(request, quest_id=None, submission_id=None, template="quest_manager/quests.html"):
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_teacher = User.objects.create_user('test_teacher', password="password", is_staff=True)
        self.test_student = User.objects.create_user('test_student', password="password")

        self.quest1 = baker.make(Quest)

    def test_quest_id_provided_to_view(self):
        """
        This test handles the view when accessed via:
        url(r'^list/(?P<quest_id>[0-9]+)/$', views.quest_list, name='quest_active'

        ... which is actually never used anywhere!

        """

        self.client.force_login(self.test_student)

        # access the view
        response = self.client.get(reverse('quests:quest_active', args=[self.quest1.id]))

        # should be on the available tab, since this quest is available (quest defaults make them available)
        self.assertTrue(response.context['available_tab_active'])
        self.assertEqual(response.context['active_q_id'], self.quest1.id)

        # TODO: test the actual content properly with selenium?
        self.assertContains(response, 'id="available"')

        # quest isn't in there yet because they haven't joined a course
        # it should also be selected and the accordian expanded, but test that stuff with selenium?
        self.assertNotContains(response, f'id="heading-quest-{self.quest1.id}')
        self.assertContains(response, 'Join a Course')

        # put the student in a course in the active semester
        baker.make('courses.CourseStudent', user=self.test_student, semester=SiteConfig.get().active_semester)

        # access the view again
        response = self.client.get(reverse('quests:quest_active', args=[self.quest1.id]))
        # should now see the quest
        self.assertContains(response, f'id="heading-quest-{self.quest1.id}')

    def test_student_sees_quests_available_outside_course(self):
        self.client.force_login(self.test_student)
        quest_avail_outside_course = baker.make(Quest, available_outside_course=True)
        response = self.client.get(reverse('quests:quest_active', args=[quest_avail_outside_course.id]))
        self.assertContains(response, f'id="heading-quest-{quest_avail_outside_course.id}')

    def test_show_hidden(self):
        """ Test of:
        url(r'^available/all/$', views.quest_list, name='available_all'),
        """
        self.client.force_login(self.test_student)
        response = self.client.get(reverse('quests:available'))
        # no hidden quests yet, so button should not appear
        self.assertNotContains(response, 'Show Hidden Quests')

        # hide a quest and try again
        self.test_student.profile.hide_quest(self.quest1.id)
        self.assertEqual(self.test_student.profile.hidden_quests, str(self.quest1.id))

        # button appears if:
        # {% if available_tab_active and remove_hidden and request.user.profile.hidden_quests and request.user.profile.has_current_course %}

        response = self.client.get(reverse('quests:available'))
        self.assertEqual(response.context['available_tab_active'], True)
        self.assertEqual(response.context['remove_hidden'], True)

        # Still not there though, because student doesn't have an active course
        self.assertNotContains(response, 'Show Hidden Quests')

        # put the student in a course in the active semester
        baker.make('courses.CourseStudent', user=self.test_student, semester=SiteConfig.get().active_semester)

        # button should be visible now
        response = self.client.get(reverse('quests:available'))
        self.assertContains(response, 'Show Hidden Quests')

        # and the quest shouldn't appear on the page:
        self.assertNotContains(response, f'id="heading-quest-{self.quest1.id}')

        # but it should appear when we view all quests
        response = self.client.get(reverse('quests:available_all'))
        self.assertContains(response, f'id="heading-quest-{self.quest1.id}')

        # and no button when already viewing hidden quests
        self.assertNotContains(response, 'Show Hidden Quests')


class CategoryViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)

        # self.category = baker.make('quests_manager.category', name="testcat")

    def test_all_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to home page or admin login '''

        self.assertRedirectsAdmin('quests:categories')
        self.assertRedirectsAdmin('quests:category_create')
        self.assertRedirectsAdmin('quests:category_update', args=[1])
        self.assertRedirectsAdmin('quests:category_delete', args=[1])

    def test_all_page_status_codes_for_students(self):
        ''' If not logged in then all views should redirect to home page or admin login '''
        self.client.force_login(self.test_student1)

        # Staff access only
        self.assertRedirectsAdmin('quests:categories')
        self.assertRedirectsAdmin('quests:category_create')
        self.assertRedirectsAdmin('quests:category_update', args=[1])
        self.assertRedirectsAdmin('quests:category_delete', args=[1])

    def test_all_page_status_codes_for_staff(self):
        ''' If not logged in then all views should redirect to home page or admin login '''
        self.client.force_login(self.test_teacher)

        # Staff access only
        self.assert200('quests:categories')

    def test_CategoryList_view(self):
        """ Admin should be able to view course list """
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('quests:categories'))
        self.assertEqual(response.status_code, 200)

    def test_CategoryCreate_view(self):

        """ Admin should be able to create a course """
        self.client.force_login(self.test_teacher)
        data = {
            'title': 'New category',
            'active': True,
        }
        response = self.client.post(reverse('quests:category_create'), data=data)
        self.assertRedirects(response, reverse('quests:categories'))

        course = Category.objects.get(title=data['title'])
        self.assertEqual(course.title, data['title'])

    def test_CategoryUpdate_view(self):
        """ Admin should be able to update a course """
        self.client.force_login(self.test_teacher)
        data = {
            'title': 'My Updated Title',
            'active': False,
        }
        response = self.client.post(reverse('quests:category_update', args=[1]), data=data)
        self.assertRedirects(response, reverse('quests:categories'))
        course = Category.objects.get(id=1)
        self.assertEqual(course.title, data['title'])
        self.assertEqual(course.active, data['active'])

    def test_CategoryDelete_view(self):
        """ Admin should be able to delete a course """
        self.client.force_login(self.test_teacher)

        before_delete_count = Category.objects.count()
        response = self.client.post(reverse('quests:category_delete', args=[Category.objects.filter(title="Orientation")[0].id]))
        after_delete_count = Category.objects.count()
        self.assertRedirects(response, reverse('quests:categories'))
        self.assertEqual(before_delete_count - 1, after_delete_count)


class AjaxQuestInfoTest(ViewTestUtilsMixin, TenantTestCase):

    """Tests for:
    def ajax_quest_info(request, quest_id=None)

    via

    url(r'^ajax_quest_info/(?P<quest_id>[0-9]+)/$', views.ajax_quest_info, name='ajax_quest_info'),
    url(r'^ajax_quest_info/$', views.ajax_quest_info, name='ajax_quest_root'),
    url(r'^ajax_quest_info/$', views.ajax_quest_info, name='ajax_quest_all'),
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_student = User.objects.create_user('test_student', password="password")
        self.client.force_login(self.test_student)
        self.quest = baker.make(Quest)
        # self.test_teacher = User.objects.create_user('test_teacher', password="password", is_staff=True)

    def test_get_returns_404(self):
        """ This view is only accessible by an ajax POST request """
        self.assert404('quests:ajax_quest_info', args=[self.quest.id])

    def test_non_ajax_post_returns_404(self):
        """ This view is only accessible by an ajax POST request """
        response = self.client.post(
            reverse('quests:ajax_quest_info', args=[self.quest.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_ajax_returns_json(self):
        response = self.client.post(
            reverse('quests:ajax_quest_info', args=[self.quest.id]),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)

        from django.http import JsonResponse
        self.assertEqual(type(response), JsonResponse)

        # Same without a quest ID:
        response = self.client.post(
            reverse('quests:ajax_quest_all'),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)

        from django.http import JsonResponse
        self.assertEqual(type(response), JsonResponse)


class AjaxApprovalInfoTest(ViewTestUtilsMixin, TenantTestCase):
    """Tests for:
    def ajax_approval_info(request, submission_id=None)

    via

    url(r'^ajax_approval_info/$', views.ajax_approval_info, name='ajax_approval_root'),
    url(r'^ajax_approval_info/(?P<submission_id>[0-9]+)/$', views.ajax_approval_info, name='ajax_approval_info'),
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_student = User.objects.create_user('test_student', password="password")
        self.client.force_login(self.test_student)
        self.quest = baker.make(Quest)
        self.submission = baker.make(QuestSubmission)
        # self.test_teacher = User.objects.create_user('test_teacher', password="password", is_staff=True)

    def test_get_returns_404(self):
        """ This view is only accessible by an ajax POST request """
        self.assert404('quests:ajax_approval_info', args=[self.submission.id])

    def test_non_ajax_post_returns_404(self):
        """ This view is only accessible by an ajax POST request """
        response = self.client.post(
            reverse('quests:ajax_approval_info', args=[self.submission.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_ajax_returns_json(self):
        response = self.client.post(
            reverse('quests:ajax_approval_info', args=[self.submission.id]),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)

        from django.http import JsonResponse
        self.assertEqual(type(response), JsonResponse)

        # includes the submission in context as s
        self.assertEqual(response.context['s'], self.submission)

        # Without a submission ID fails, 404:
        response = self.client.post(
            reverse('quests:ajax_approval_root'),  # what the heck is this used for?!
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 404)


class AjaxSubmissionInfoTest(ViewTestUtilsMixin, TenantTestCase):
    """Tests for:
    def ajax_submission_info(request, submission_id=None)

    via

    url(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/$', views.ajax_submission_info, name='ajax_info_in_progress'),
    url(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/past/$', views.ajax_submission_info, name='ajax_info_past'),
    url(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/completed/$', views.ajax_submission_info,
        name='ajax_info_completed'),
    url(r'^ajax_submission_info/$', views.ajax_submission_info, name='ajax_submission_root'),
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_student = User.objects.create_user('test_student', password="password")
        self.client.force_login(self.test_student)
        self.quest = baker.make(Quest)
        self.submission = baker.make(QuestSubmission, user=self.test_student)
        # self.test_teacher = User.objects.create_user('test_teacher', password="password", is_staff=True)

    def test_get_returns_404(self):
        """ This view is only accessible by an ajax POST request """
        self.assert404('quests:ajax_info_in_progress', args=[self.submission.id])

    def test_non_ajax_post_returns_404(self):
        """ This view is only accessible by an ajax POST request """
        response = self.client.post(
            reverse('quests:ajax_info_in_progress', args=[self.submission.id])
        )
        self.assertEqual(response.status_code, 404)

    def test_ajax_info_in_progress(self):
        response = self.client.post(
            reverse('quests:ajax_info_in_progress', args=[self.submission.id]),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)

        from django.http import JsonResponse
        self.assertEqual(type(response), JsonResponse)

        # Check context variables
        self.assertEqual(response.context['s'], self.submission)
        self.assertEqual(response.context['completed'], False)
        self.assertEqual(response.context['past'], False)

        # Without a submission ID fails, 404:
        response = self.client.post(
            reverse('quests:ajax_submission_root'),  # what the heck is this used for?!
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 404)

    def test_ajax_info_completed(self):
        """ url(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/completed/$', views.ajax_submission_info,
        name='ajax_info_completed')
        """
        response = self.client.post(
            reverse('quests:ajax_info_completed', args=[self.submission.id]),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )

        # Submission is NOT complete, so doesn't find it.
        # ? Is it a problem if it DOES find it?  If not, we don't need to test that possibility
        self.assertEqual(response.status_code, 404)

        # complete the submission
        self.submission.mark_completed()
        # Also needs to be current semester submission
        self.submission.semester = SiteConfig.get().active_semester
        self.submission.save()
        response = self.client.post(
            reverse('quests:ajax_info_completed', args=[self.submission.id]),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(response.status_code, 200)

        # Check context variables
        self.assertEqual(response.context['s'], self.submission)
        self.assertEqual(response.context['completed'], True)
        self.assertEqual(response.context['past'], False)

    def test_ajax_info_past(self):
        """ Completed and in a past semester

        url(r'^ajax_submission_info/(?P<submission_id>[0-9]+)/past/$', views.ajax_submission_info, name='ajax_info_past')
        """
        self.submission.mark_completed()
        response = self.client.post(
            reverse('quests:ajax_info_past', args=[self.submission.id]),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        # Submission is NOT in current semester (cus setUp doesn't put it there)
        self.assertEqual(response.status_code, 200)

        # Check context variables
        self.assertEqual(response.context['s'], self.submission)
        self.assertEqual(response.context['completed'], False)
        self.assertEqual(response.context['past'], True)


class DetailViewTest(ViewTestUtilsMixin, TenantTestCase):
    """ Tests for:

            def detail(request, quest_id):

            via

            url(r'^(?P<quest_id>[0-9]+)/$', views.detail, name='quest_detail'),
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_student = User.objects.create_user('test_student', password="password")
        self.client.force_login(self.test_student)

        self.quest = baker.make(Quest, name="Test Quest")

    def test_quest_is_available(self):
        with patch('quest_manager.models.Quest.is_available', return_value=True):
            response = self.client.get(reverse('quests:quest_detail', args=[self.quest.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['available'])

    def test_quest_is_editable(self):
        with patch('quest_manager.models.Quest.is_editable', return_value=True):
            response = self.client.get(reverse('quests:quest_detail', args=[self.quest.id]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['available'])

    def test_quest_is_not_available_nor_editable(self):
        """ Should only display a preview version of the quest
        """

        # Quest won't be editable by a student by default, so no need to patch that
        with patch('quest_manager.models.Quest.is_available', return_value=False):
            response = self.client.get(reverse('quests:quest_detail', args=[self.quest.id]))

        # they don't have a submission in progress, so display a restricted version
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context['available'])

        self.assertContains(response, "Quest Preview")  # Should be something on the page indicating it's a preview
        self.assertNotContains(response, "Start Quest")  # Definitely no "Start Quest" button

    def test_quest_is_not_available_nor_editable_but_submission_exists(self):
        """ If they have a submission, it should redirect to that,
        otherwise only display a (preview) version of the quest
        """

        # create a submission for them.  Doesn't have to be current semester
        sub = baker.make(QuestSubmission, quest=self.quest, user=self.test_student)

        # Quest won't be editable by a student by default, so no need to patch that
        with patch('quest_manager.models.Quest.is_available', return_value=False):
            response = self.client.get(reverse('quests:quest_detail', args=[self.quest.id]))

        # Should redirect them to the submission's page
        self.assertRedirects(response, reverse('quests:submission', args=[sub.id]))


class ApproveViewTest(ViewTestUtilsMixin, TenantTestCase):
    """ Tests for:

            def approve(request, submission_id):

            via

            url(r'^submission/(?P<submission_id>[0-9]+)/approve/$', views.approve, name='approve'),
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.test_student = User.objects.create_user('test_student', password="password")
        self.test_teacher = User.objects.create_user('test_teacher', password="password", is_staff=True)
        self.client.force_login(self.test_teacher)

        self.quest = baker.make(Quest, name="Test Quest")
        self.sub = baker.make(QuestSubmission, quest=self.quest, user=self.test_student)

    def test_get_404(self):
        """ This view is only accessible via POST """
        self.assert404('quests:approve', args=[self.sub.id])

    def test_approve_with_comment_only_quick_reply_form(self):
        comment_text = "Lorum Ipsum"
        quick_reply_form_data = {
            'comment_text': comment_text,
            'approve_button': True
        }

        response = self.client.post(
            reverse('quests:approve', args=[self.sub.id]),
            data=quick_reply_form_data
        )
        self.assertRedirects(response, reverse('quests:approvals'))

        # This submission should now be approved
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.is_approved)

        # And the submission should have a comment
        from comments.models import Comment
        comments = Comment.objects.all_with_target_object(self.sub)
        self.assertEqual(comments.count(), 1)
        self.assertEqual(comments.first().text, comment_text)

        # And the student should have a notification
        # get_user_target is a weird method, should probably be refactored or better documented...
        notification_for_sub = Notification.objects.get_user_target(self.test_student, self.sub)
        self.assertTrue(notification_for_sub)  # not empty or blank or None...etc

        # And the approver should have gotten a django success message
        # Why doesn't this work?
        # https://stackoverflow.com/questions/2897609/how-can-i-unit-test-django-messages
        # messages = list(response.context['messages'])
        # self.assertEqual(len(messages), 1)
        # self.assertEqual(messages[0].tags, 'success')

    def test_approve_with_badge_quick_reply_form(self):
        """ Test that the badge is granted """
        test_badge = baker.make('badges.Badge')
        comment_text = "Lorum Ipsum"
        quick_reply_form_data = {
            'comment_text': comment_text,
            'approve_button': True,
            'award': test_badge.id  # Note single award only for quick reply form
        }

        # Before, user has earned no badges
        badges_earned = self.test_student.badgeassertion_set.filter(badge=test_badge)
        self.assertEqual(badges_earned.count(), 0)

        response = self.client.post(
            reverse('quests:approve', args=[self.sub.id]),
            data=quick_reply_form_data
        )
        self.assertRedirects(response, reverse('quests:approvals'))

        # check that badge was awarded
        badges_earned = self.test_student.badgeassertion_set.filter(badge=test_badge)
        self.assertEqual(badges_earned.count(), 1)

    def test_approve_other_teachers_student(self):
        """ When a teacher approves/rejects/comments on another teacher's student
        The student's actual teacher(s) should get notified

        self.test_teacher is logged in and approving submission in this test,
        so create another user as the current teacher
        """
        current_teacher = baker.make(User, is_staff=True)

        # ? Can't figure out how to mock this... so I guess need to actually setup the data structures
        # with patch('quest_manager.views.QuestSubmission.user.profile.get_current_teacher_list', return_value=[current_teacher]):
        # with patch('quest_manager.views.Profile.get_current_teacher_list', return_value=[current_teacher]):
        # with patch('profile_manager.models.Profile.get_current_teacher_list', return_value=[current_teacher]):
        # with patch('quest_manager.models.QuestSubmission.user.profile.get_current_teacher_list', return_value=[current_teacher]):
        # with patch('profile_manager.models.CourseStudent.objects.get_current_teacher_list', return_value=[current_teacher]):
        #     response = self.client.get(reverse('quests:quest_detail', args=[self.quest.id]))

        # # ! Gotta put student in a course with another teacher until I can figure out how to mock it.  failed attempts above.
        # test_block = baker.make('courses.Block', teacher=current_teacher)
        # baker.make('courses.StudentCourse', user=self.test_user, block=test_block)

        # response = self.client.get(reverse('quests:quest_detail', args=[self.quest.id]))

        comment_text = "Lorum Ipsum"
        quick_reply_form_data = {
            'comment_text': comment_text,
            'approve_button': True
        }

        # self.test_teacher is logged in in setUp()
        with patch('profile_manager.models.CourseStudent.objects.get_current_teacher_list', return_value=[current_teacher.id]):
            response = self.client.post(
                reverse('quests:approve', args=[self.sub.id]),
                data=quick_reply_form_data
            )
            self.assertRedirects(response, reverse('quests:approvals'))

        # The student AND current_teacher should have a notification
        # get_user_target is a weird method, should probably be refactored or better documented...
        notification_for_sub = Notification.objects.get_user_target(self.test_student, self.sub)
        self.assertTrue(notification_for_sub)  # not empty or blank or None...etc
        # The student's current teacher also gets a notification
        notification_for_sub = Notification.objects.get_user_target(current_teacher, self.sub)
        self.assertTrue(notification_for_sub)

    def test_approve_without_comment(self):
        """ If no comment is provided when approving a quest, then the default approval comment from SiteConfig should be used"""
        quick_reply_form_data = {'comment_text': "", 'approve_button': True}
        self.client.post(reverse('quests:approve', args=[self.sub.id]), data=quick_reply_form_data)

        # Submission should now have a comment with the default approved comment text
        from comments.models import Comment
        comments = Comment.objects.all_with_target_object(self.sub)
        self.assertEqual(comments.count(), 1)
        self.assertEqual(comments.first().text, SiteConfig.get().blank_approval_text)

    def test_approve_with_mutiple_badges_staff_submission_form(self):
        """ Test that multiple badges can be granted from the SubmissionFormStaff form"""
        test_badge1 = baker.make('badges.Badge')
        test_badge2 = baker.make('badges.Badge')
        comment_text = "Lorum Ipsum"
        staff_form_data = {
            'approve_button': True,
            'comment_text': comment_text,
            'awards': [test_badge1.pk, test_badge2.pk]  # This is what triggers the logic to look for the other form.... bad!?
        }

        # no badges yet
        badges_earned = self.test_student.badgeassertion_set.all()
        self.assertEqual(badges_earned.count(), 0)

        response = self.client.post(
            reverse('quests:approve', args=[self.sub.id]),
            data=staff_form_data
        )
        self.assertRedirects(response, reverse('quests:approvals'))

        # check that two badges were awarded
        badges_earned = self.test_student.badgeassertion_set.all()
        self.assertEqual(badges_earned.count(), 2)

        self.sub.refresh_from_db()
        self.assertTrue(self.sub.is_approved)

        # And the submission should have a comment
        from comments.models import Comment
        comments = Comment.objects.all_with_target_object(self.sub)
        self.assertEqual(comments.count(), 1)
        self.assertIn(comment_text, comments.first().text)
        # Also there should be a note in the comment about each badge awarded:
        self.assertIn(test_badge1.name, comments.first().text)
        self.assertIn(test_badge2.name, comments.first().text)

        # And the student should have a notification
        # get_user_target is a weird method, should probably be refactored or better documented...
        notification_for_sub = Notification.objects.get_user_target(self.test_student, self.sub)
        self.assertTrue(notification_for_sub)  # not empty or blank or None...etc

    def test_approve_with_files_submission_form(self):
        """ Files can be uploaded and attached to comments when approving/commenting/rejecting quests
        and a link to the file is included in the comment.
        """
        # # create a file for testing
        # from django.core.files.uploadedfile import SimpleUploadedFile
        # # give it a unique name for easier testing, otherwise when re-testing,
        # # the name will be appended with stuff because the file already exists
        # import uuid
        # test_filename1 = str(uuid.uuid1().hex) + ".txt"
        # test_file1 = SimpleUploadedFile(test_filename1, b"file_content1", 'text/plain')
        # test_filename2 = str(uuid.uuid1().hex) + ".txt"
        # test_file2 = SimpleUploadedFile(test_filename2, b"file_content2", 'text/plain')
        test_files = create_two_test_files()
        staff_form_data = {
            'approve_button': True,
            'attachments': test_files
        }
        response = self.client.post(
            reverse('quests:approve', args=[self.sub.id]),
            staff_form_data,
        )
        self.assertRedirects(response, reverse('quests:approvals'))

        # make sure the files exist
        from comments.models import Comment
        comment = Comment.objects.all_with_target_object(self.sub).first()
        self.assertTrue(comment)  # not empty or None etc
        comment_files_qs = comment.document_set.all()
        self.assertEqual(comment_files_qs.count(), 2)

        # make sure they are the correct
        comment_files = list(comment_files_qs)  # evalute qs so we can slice without weirdness
        import os
        self.assertEqual(os.path.basename(comment_files[0].docfile.name), test_files[0].name)
        self.assertEqual(os.path.basename(comment_files[1].docfile.name), test_files[1].name)

    def test_comment_button(self):
        """ The comment button should only leave a comment and not change the status of the submission """
        comment_text = "Lorum Ipsum"
        quick_reply_form_data = {
            'comment_text': comment_text,
            'comment_button': True
        }

        response = self.client.post(
            reverse('quests:approve', args=[self.sub.id]),
            data=quick_reply_form_data
        )
        self.assertRedirects(response, reverse('quests:approvals'))

        # This submission should NOT be approved because it was only commented on, not approved
        self.sub.refresh_from_db()
        self.assertFalse(self.sub.is_approved)

        # And the submission should have a comment
        from comments.models import Comment
        comments = Comment.objects.all_with_target_object(self.sub)
        self.assertEqual(comments.count(), 1)
        self.assertEqual(comments.first().text, comment_text)

        # And the student should have a notification
        # get_user_target is a weird method, should probably be refactored or better documented...
        notification_for_sub = Notification.objects.get_user_target(self.test_student, self.sub)
        self.assertTrue(notification_for_sub)  # not empty or blank or None...etc

    def test_return_button(self):
        """ The return button should mark the submission as returned """
        comment_text = "Lorum Ipsum"
        form_data = {'comment_text': comment_text, 'return_button': True}

        response = self.client.post(reverse('quests:approve', args=[self.sub.id]), data=form_data)
        self.assertRedirects(response, reverse('quests:approvals'))

        # This submission should be marked as returned
        self.sub.refresh_from_db()
        self.assertTrue(self.sub.is_returned)

    def test_no_comment_return_button(self):
        """ When a submission is returned without comment, the SiteConfig's blank_return_text should be inserted """

        form_data = {'comment_text': "", 'return_button': True}

        response = self.client.post(reverse('quests:approve', args=[self.sub.id]), data=form_data)
        self.assertRedirects(response, reverse('quests:approvals'))

        from comments.models import Comment
        comments = Comment.objects.all_with_target_object(self.sub)
        self.assertEqual(comments.count(), 1)
        self.assertEqual(comments.first().text, SiteConfig.get().blank_return_text)

    def test_non_existant_submit_button(self):
        """Can this even happen?  Somehow the form was submitted with a button that doesn't exist"""
        form_data = {'non_existant_submit_button': True}
        response = self.client.post(reverse('quests:approve', args=[self.sub.id]), data=form_data)
        self.assertEqual(response.status_code, 404)


class ApprovalsViewTest(ViewTestUtilsMixin, TenantTestCase):
    """ Tests for:

            def approvals(request, quest_id=None):

            via

            url(r'^approvals/$', views.approvals, name='approvals'),
            url(r'^approvals/submitted/$', views.approvals, name='submitted'),
            url(r'^approvals/submitted/all/$', views.approvals, name='submitted_all'),
            url(r'^approvals/returned/$', views.approvals, name='returned'),
            url(r'^approvals/approved/$', views.approvals, name='approved'),
            url(r'^approvals/flagged/$', views.approvals, name='flagged'),
            url(r'^approvals/approved/(?P<quest_id>[0-9]+)/$', views.approvals, name='approved_for_quest'),
            url(r'^approvals/approved/(?P<quest_id>[0-9]+)/all/$', views.approvals, name='approved_for_quest_all'),
            # Unused:
            # url(r'^approvals/skipped/$', views.approvals, name='skipped'),
            # url(r'^approvals/submitted/(?P<quest_id>[0-9]+)/$', views.approvals, name='submitted_for_quest'),  # Not used
            # url(r'^approvals/returned/(?P<quest_id>[0-9]+)/$', views.approvals, name='returned_for_quest'), # Not used
            # url(r'^approvals/skipped/(?P<quest_id>[0-9]+)/$', views.approvals, name='skipped_for_quest'), # Not used
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)

        # A teacher with a student (connected by the Block in the CourseStudent)
        self.test_student = User.objects.create_user('test_student', password="password")
        self.current_teacher = User.objects.create_user('test_current_teacher', password="password", is_staff=True)
        # current_teacher_block = baker.make('courses.Block', current_teacher=self.current_teacher)
        # baker.make('courses.CourseStudent', block=current_teacher_block, user=self.test_student, semester=SiteConfig.get().active_semester)

        self.client.force_login(self.current_teacher)

        # Don't need these, just patch where needed
        # A different student with a different teacher (in a different Block)
        # self.test_student_of_other_teacher = User.objects.create_user('test_student_of_other_teacher', password="password")
        # self.other_teacher = User.objects.create_user('test_other_teacher', password="password", is_staff=True)
        # other_teacher_block = baker.make('courses.Block', current_teacher=self.other_teacher)
        # baker.make('courses.CourseStudent', block=other_teacher_block, user=self.test_student, semester=SiteConfig.get().active_semester)

        self.quest = baker.make(Quest, name="Test Quest")
        self.sub = baker.make(QuestSubmission, quest=self.quest)

    def test_submitted(self):
        """ Completed quests awaiting approval for current teacher (teachers are connected by Block)
        A student in a course (StudentCourse) in the teacher's block (Block) should have their submissions
        appear here
        """
        with patch('quest_manager.views.QuestSubmission.objects.all_awaiting_approval', return_value=[self.sub]):
            response = self.client.get(reverse('quests:submitted'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.sub))
        self.assertTrue(response.context['submitted_tab_active'])  # ? Is this used anymore?
        # Tabs: 0-Submitted, 1-Returned, 2-Approved, 3- Flagged
        self.assertTrue(response.context['tab_list'][0]['active'])
        self.assertTrue(response.context['current_teacher_only'])
        self.assertIsNone(response.context['quest'])
        self.assertURLEqual(response.context['tab_list'][0]['url'], reverse('quests:submitted'))

    def test_submitted_all(self):
        """ All completed quests awaiting approvel, even for students with another teacher (teachers are connected by Block)
        """
        with patch('quest_manager.views.QuestSubmission.objects.all_awaiting_approval', return_value=[self.sub]):
            response = self.client.get(reverse('quests:submitted_all'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.sub))
        # Tabs: 0-Submitted, 1-Returned, 2-Approved, 3- Flagged
        self.assertTrue(response.context['tab_list'][0]['active'])
        self.assertFalse(response.context['current_teacher_only'])
        self.assertIsNone(response.context['quest'])
        self.assertURLEqual(response.context['tab_list'][0]['url'], reverse('quests:submitted'))

    def test_returned(self):
        """ Completed quests for current teacher that have been returned to the student. """
        with patch('quest_manager.views.QuestSubmission.objects.all_returned', return_value=[self.sub]):
            response = self.client.get(reverse('quests:returned'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.sub))
        # Tabs: 0-Submitted, 1-Returned, 2-Approved, 3- Flagged
        self.assertTrue(response.context['tab_list'][1]['active'])
        self.assertTrue(response.context['current_teacher_only'])
        self.assertIsNone(response.context['quest'])
        self.assertURLEqual(response.context['tab_list'][1]['url'], reverse('quests:returned'))

    def test_approved(self):
        """ Completed quests (submissions) that have been approved by a teacher """

        with patch('quest_manager.views.QuestSubmission.objects.all_approved', return_value=[self.sub]):
            response = self.client.get(reverse('quests:approved'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.sub))
        # Tabs: 0-Submitted, 1-Returned, 2-Approved, 3- Flagged
        self.assertTrue(response.context['tab_list'][2]['active'])
        self.assertTrue(response.context['current_teacher_only'])
        self.assertIsNone(response.context['quest'])
        self.assertURLEqual(response.context['tab_list'][2]['url'], reverse('quests:approved'))

    def test_flagged(self):
        with patch('quest_manager.views.QuestSubmission.objects.flagged', return_value=[self.sub]):
            response = self.client.get(reverse('quests:flagged'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.sub))
        # Tabs: 0-Submitted, 1-Returned, 2-Approved, 3- Flagged
        self.assertTrue(response.context['tab_list'][3]['active'])
        self.assertTrue(response.context['current_teacher_only'])
        self.assertIsNone(response.context['quest'])
        self.assertURLEqual(response.context['tab_list'][3]['url'], reverse('quests:flagged'))

    # def test_skipped(self):
    #     with patch('quest_manager.views.QuestSubmission.objects.all_skipped', return_value=[self.sub]):
    #         response = self.client.get(reverse('quests:skipped'))
    #     self.assertEqual(response.status_code, 200)
    #     self.assertContains(response, str(self.sub))
    #     # Tabs: 0-Submitted, 1-Returned, 2-Approved, 3- Skipped
    #     self.assertTrue(response.context['tab_list'][3]['active'])
    #     self.assertTrue(response.context['current_teacher_only'])
    #     self.assertIsNone(response.context['quest'])
    #     self.assertURLEqual(response.context['tab_list'][3]['url'], reverse('quests:skipped'))

    def test_approved_for_quest(self):
        """ Approved submissions of only this specific quest, regardless of teacher """

        with patch('quest_manager.views.QuestSubmission.objects.all_approved', return_value=[self.sub]):
            response = self.client.get(reverse('quests:approved_for_quest', args=[self.quest.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, str(self.sub))
        # Tabs: 0-Submitted, 1-Returned, 2-Approved, 3- Flagged
        self.assertTrue(response.context['tab_list'][2]['active'])
        self.assertTrue(response.context['current_teacher_only'])
        self.assertEqual(response.context['quest'], self.quest)
        self.assertURLEqual(response.context['tab_list'][2]['url'], reverse('quests:approved'))

    def test_approved_for_quest_all(self):
        """ Approved submissions of only this specific quest, regardless of teacher """
        pass

    def test_approvals_all_buttons_does_not_exist(self):
        """ My blocks should not be rendered when there is only one teacher"""

        response = self.client.get(reverse('quests:approvals'))
        self.assertNotContains(response, 'My blocks')

    def test_approval_all_button_exists(self):
        """ My blocks button should not be rendered """

        baker.make('courses.Block', block='A', current_teacher=self.current_teacher)
        baker.make('courses.Block', block='B', current_teacher=self.current_teacher)

        another_teacher = baker.make(User, is_staff=True)
        baker.make('courses.Block', block='C', current_teacher=another_teacher)
        baker.make('courses.Block', block='D', current_teacher=another_teacher)

        response = self.client.get(reverse('quests:approvals'))
        self.assertContains(response, 'My blocks')
