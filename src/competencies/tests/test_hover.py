from django.contrib.auth import get_user_model
from django.urls import reverse

from model_bakery import baker

from comments.models import Comment
from competencies.models import Competency, QuestCompetency
from competencies.tests.test_approval import set_competencies_flag
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()

DESCRIPTION = 'Communicating encompasses the abilities people use to "impart" & exchange information.'


class CompetencyFullTextTest(ByteDeckTenantTestCase):
    """ Tests for Competency.full_text, the hover text wherever a competency is named. """

    def test_full_text__the_qualified_name_without_a_description(self):
        """ With no description, it's the qualified name: course, category and the whole name """
        competency = baker.make(Competency, course="ADST 9", category="Defining", name="Choose a design opportunity", description="")

        self.assertEqual(competency.full_text, "ADST 9: Defining: Choose a design opportunity")

    def test_full_text__then_the_description(self):
        """ With a description, the description follows the qualified name, a blank line between """
        competency = baker.make(Competency, course="Core", category="Communication", name="Communicating", description=DESCRIPTION)

        self.assertEqual(competency.full_text, f"Core: Communication: Communicating\n\n{DESCRIPTION}")


class CompetencyHoverTextPagesTest(ByteDeckTenantTestCase):
    """ The pages and comments that name a competency give its full text as the name's hover text. """

    def setUp(self):
        """ Competencies on, a teacher signed in, and a Core competency with a description linked to a quest. """
        set_competencies_flag(True)
        self.teacher = User.objects.create_user('hover_teacher', is_staff=True)
        self.client.force_login(self.teacher)
        self.competency = baker.make(Competency, course="Core", category="Communication", name="Communicating", description=DESCRIPTION)
        self.quest = baker.make(Quest, name="Hover Quest", published=True)
        QuestCompetency.objects.create(quest=self.quest, competency=self.competency)
        self.title = (
            'title="Core: Communication: Communicating\n\n'
            'Communicating encompasses the abilities people use to &quot;impart&quot; &amp; exchange information."'
        )

    def test_list__each_name_with_its_full_text(self):
        """ The staff list of competencies gives each name its full text on hover """
        response = self.client.get(reverse('competencies:list'))

        self.assertContains(response, f'<td {self.title}>Communicating</td>')

    def test_quest_info__each_name_with_its_full_text(self):
        """ The Quest Info's competencies give their full text on hover, description included """
        response = self.client.get(reverse('quests:quest_detail', args=[self.quest.pk]))

        self.assertContains(response, f'<li {self.title}>Communicating</li>')

    def test_quest_form__each_default_level_row_with_its_full_text(self):
        """ The quest form's default-level rows give each competency's full text on hover """
        response = self.client.get(reverse('quests:quest_update', args=[self.quest.pk]))

        self.assertContains(response, self.title + '>Communicating</label>')

    def test_approval_comment__the_full_text_in_each_title(self):
        """ The levels an approval lists in its comment give each competency's full text on hover """
        submission = baker.make(
            QuestSubmission, quest=self.quest, user=baker.make(User), is_completed=True, semester=SiteConfig.get().active_semester,
        )

        self.client.post(reverse('quests:approve', args=[submission.pk]), data={'approve_button': True, 'comment_text': ''})

        text = Comment.objects.filter(target_object_id=submission.pk).order_by('-pk').first().text
        # the comment cleaner writes the title back in single quotes, as it contains double ones
        self.assertIn(
            "<span title='Core: Communication: Communicating\n\n"
            'Communicating encompasses the abilities people use to "impart" &amp; exchange information.\'>'
            'Communicating</span>: <b>Proficient</b>', text,
        )
