# Create your tests here.
import djconfig
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from model_mommy import mommy

from quest_manager.models import QuestSubmission, Quest


class QuestViewTests(TestCase):

    # includes some basic model data
    # fixtures = ['initial_data.json']

    def setUp(self):
        djconfig.reload_maybe()  # https://github.com/nitely/django-djconfig/issues/31#issuecomment-451587942

        User = get_user_model()

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = mommy.make(User)

        self.quest1 = mommy.make(Quest)
        self.quest2 = mommy.make(Quest)

        self.sub1 = mommy.make(QuestSubmission, user=self.test_student1, quest=self.quest1)
        self.sub2 = mommy.make(QuestSubmission, quest=self.quest1)

    def test_all_quest_page_status_codes_for_anonymous(self):
        """ If not logged in then all views should redirect to home page  """

        self.assertRedirects(
            response=self.client.get(reverse('quest_manager:quests')),
            expected_url='%s?next=%s' % (reverse('home'), reverse('quest_manager:quests')),
        )

    def test_all_quest_page_status_codes_for_students(self):

        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        s_pk = self.test_student1.pk
        s2_pk = self.test_student2.pk
        q_pk = self.quest1.pk

        self.assertEquals(self.client.get(reverse('quest_manager:quests')).status_code, 200)
        self.assertEquals(self.client.get(reverse('quest_manager:available')).status_code, 200)
        self.assertEquals(self.client.get(reverse('quest_manager:available2')).status_code, 200)
        self.assertEquals(self.client.get(reverse('quest_manager:inprogress')).status_code, 200)
        self.assertEquals(self.client.get(reverse('quest_manager:completed')).status_code, 200)
        self.assertEquals(self.client.get(reverse('quest_manager:past')).status_code, 200)
        # anyone can view drafts if they figure out the url, but it will be blank for them
        self.assertEquals(self.client.get(reverse('quest_manager:drafts')).status_code, 200)

        self.assertEquals(self.client.get(reverse('quest_manager:quest_detail',
                                                  args=[q_pk])).status_code, 200)
        self.assertEquals(self.client.get(reverse('quest_manager:quest_detail',
                                                  args=[q_pk])).status_code, 200)

        #  students shouldn't have access to these and should be redirected to login
        self.assertEquals(self.client.get(reverse('quest_manager:submitted')).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:submitted_all')).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:returned')).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:approved')).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:skipped')).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:submitted_for_quest', args=[q_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:returned_for_quest', args=[q_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:approved_for_quest', args=[q_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:approved_for_quest_all', args=[q_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:skipped_for_quest', args=[q_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:quest_create')).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:quest_update', args=[q_pk])).status_code, 302)

        self.assertEquals(self.client.get(reverse('quest_manager:quest_copy', args=[q_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:quest_delete', args=[q_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:start', args=[q_pk])).status_code, 404)
        self.assertEquals(self.client.get(reverse('quest_manager:hide', args=[q_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:unhide', args=[q_pk])).status_code, 302)
        self.assertEquals(self.client.get(reverse('quest_manager:skip_for_quest', args=[q_pk])).status_code, 404)

    # def test_all_quest_page_status_codes_for_teachers(self):
    #     # log in a teacher
    #     success = self.client.login(username=self.test_teacher.username, password=self.test_password)
    #     self.assertTrue(success)
    #
    #     s_pk = self.test_student1.pk
    #     s2_pk = self.test_student2.pk
    #
    #     self.assertEquals(self.client.get(reverse('profiles:profile_detail', args=[s_pk])).status_code, 200)
    #     self.assertEquals(self.client.get(reverse('profiles:profile_update', args=[s_pk])).status_code, 200)
    #     self.assertEquals(self.client.get(reverse('profiles:profile_list')).status_code, 200)
    #     self.assertEquals(self.client.get(reverse('profiles:profile_list_current')).status_code, 200)
    #     self.assertEquals(self.client.get(reverse('profiles:comment_ban', args=[s_pk])).status_code, 302)
    #     self.assertEquals(self.client.get(reverse('profiles:comment_ban_toggle', args=[s_pk])).status_code, 302)
    #     self.assertEquals(self.client.get(reverse('profiles:GameLab_toggle', args=[s_pk])).status_code, 302)
    #     # self.assertEquals(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)
    #
    # def test_profile_recalculate_xp_status_codes(self):
    #     """Need to test this view with students in an active course"""
    #     sem = mommy.make(Semester)
    #     # since there's only one semester, it should be by default the active_semester (pk=1)
    #     self.assertEquals(sem.pk, djconfig.config.hs_active_semester)
    #     self.assertEquals(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)
