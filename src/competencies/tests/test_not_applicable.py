from django.urls import reverse

from comments.models import Comment
from competencies.assessments import NOT_APPLICABLE, NotApplicable, posted_level, record_approval_assessments, starting_level
from competencies.forms import competency_level_field_name
from competencies.models import CompetencyAssessment, ProficiencyLevel, QuestCompetency
from competencies.tests.test_approval import ApprovalTestMixin, set_competencies_flag
from hackerspace_online.tests.utils import ByteDeckTenantTestCase

DEV, PRF, EXT = ProficiencyLevel.DEVELOPING, ProficiencyLevel.PROFICIENT, ProficiencyLevel.EXTENDING


class NotApplicableTestMixin(ApprovalTestMixin):
    """ Competencies on, the teacher signed in, and a submission of the quest (Critical Thinking
    defaulting to Extending, Communicating to Proficient) awaiting approval. """

    def setUp(self):
        """ Turn competencies on and sign the teacher in. """
        set_competencies_flag(True)
        self.client.force_login(self.teacher)
        self.submission = self.make_submission()
        self.thinking_field = competency_level_field_name(self.thinking.pk)
        self.communicating_field = competency_level_field_name(self.communicating.pk)

    def post_decision(self, button, **data):
        """ Post a decision on this test's submission from the approvals page's quick reply form.

        Returns:
            HttpResponse: the view's response.
        """
        return self.client.post(reverse('quests:approve', args=[self.submission.pk]), data={button: True, 'comment_text': '', **data})

    def latest_comment(self):
        """ The text of the latest comment on this test's submission. """
        return Comment.objects.filter(target_object_id=self.submission.pk).order_by('-pk').first().text


class NotApplicableLevelsTest(NotApplicableTestMixin, ByteDeckTenantTestCase):
    """ Tests for the N/A choice in posted_level and starting_level. """

    def link(self, competency):
        """ The quest's link to a competency. """
        return QuestCompetency.objects.get(quest=self.quest, competency=competency)

    def test_posted_level__na_is_none(self):
        """ N/A posts as no level; a level posts as itself; anything else falls back to the start """
        link = self.link(self.thinking)

        self.assertIsNone(posted_level({self.thinking_field: NOT_APPLICABLE}, link, PRF))
        self.assertEqual(posted_level({self.thinking_field: str(DEV)}, link, PRF), DEV)
        self.assertEqual(posted_level({self.thinking_field: 'nonsense'}, link, PRF), PRF)
        self.assertIsNone(posted_level({}, link, None))

    def test_starting_level__na_on_an_approved_submission_with_no_level(self):
        """ The form starts on the submission's level; with none, on N/A once it's approved, or the
        link's default while it's being approved """
        link = self.link(self.thinking)

        self.assertEqual(starting_level(link, {self.thinking.pk: DEV}, approved=True), DEV)
        self.assertIsNone(starting_level(link, {}, approved=True))
        self.assertEqual(starting_level(link, {}), EXT)


class NotApplicableApprovalTest(NotApplicableTestMixin, ByteDeckTenantTestCase):
    """ Choosing N/A when approving or re-rating records no level for the competency. """

    def test_approve__na_records_no_level_and_lists_it(self):
        """ A competency approved as N/A gets no level while the others get theirs, and the comment
        lists it as N/A """
        self.post_decision('approve_button', **{self.thinking_field: NOT_APPLICABLE})

        self.assertEqual(self.recorded(self.submission), {self.communicating: PRF})
        comment = self.latest_comment()
        self.assertIn('<span title="Thinking: Critical Thinking">Critical Thinking</span>: <b>N/A</b>', comment)
        self.assertIn('<span title="Communication: Communicating">Communicating</span>: <b>Proficient</b>', comment)

    def test_record_approval_assessments__na_is_returned(self):
        """ The N/A comes back beside the assessments recorded, standing for the level not recorded """
        recorded = record_approval_assessments(self.submission, self.teacher, {self.thinking_field: NOT_APPLICABLE})

        self.assertIn(NotApplicable(self.thinking), recorded)
        self.assertEqual([item.competency for item in recorded if isinstance(item, CompetencyAssessment)], [self.communicating])

    def test_approve_again__na_clears_the_earlier_level(self):
        """ A submission returned and approved again with N/A loses the level it had """
        self.post_decision('approve_button')
        self.post_decision('return_button')
        self.assertEqual(self.recorded(self.submission), {self.thinking: EXT, self.communicating: PRF})

        self.post_decision('approve_button', **{self.thinking_field: NOT_APPLICABLE, self.communicating_field: str(PRF)})

        self.assertEqual(self.recorded(self.submission), {self.communicating: PRF})

    def test_comment__na_clears_a_level(self):
        """ Re-rating an approved submission's competency to N/A clears its level and lists it in the comment """
        self.post_decision('approve_button')

        self.post_decision('comment_button', comment_text='Not shown in this one', **{
            self.thinking_field: NOT_APPLICABLE, self.communicating_field: str(PRF),
        })

        self.assertEqual(self.recorded(self.submission), {self.communicating: PRF})
        self.assertIn('Critical Thinking</span>: <b>N/A</b>', self.latest_comment())
        self.assertNotIn('Communicating</span>', self.latest_comment())

    def test_comment__a_competency_with_no_level_starts_on_na(self):
        """ On an approved submission, a competency it has no level in (approved as N/A, or added to the
        quest since) starts on N/A: commenting with it left there records nothing, and choosing a level,
        even the link's default, records that level """
        self.post_decision('approve_button', **{self.thinking_field: NOT_APPLICABLE})

        self.post_decision('comment_button', comment_text='Thanks', **{self.thinking_field: NOT_APPLICABLE, self.communicating_field: str(PRF)})
        self.assertEqual(self.recorded(self.submission), {self.communicating: PRF})
        self.assertNotIn('Competencies:', self.latest_comment())

        self.post_decision('comment_button', comment_text='On reflection', **{self.thinking_field: str(EXT), self.communicating_field: str(PRF)})
        self.assertEqual(self.recorded(self.submission), {self.thinking: EXT, self.communicating: PRF})
        self.assertIn('Critical Thinking</span>: <b>Extending</b>', self.latest_comment())


class NotApplicableWidgetTest(NotApplicableTestMixin, ByteDeckTenantTestCase):
    """ The N/A button on the approval form's level controls. """

    def na_button(self, field, checked=False):
        """ The N/A button's markup for a level field, selected or not. """
        active = ' active' if checked else ''
        selected = ' checked' if checked else ''
        return (
            f'<label class="btn btn-default competency-level-na{active}" title="Not applicable: no level is recorded for this competency">\n'
            f'        <input type="radio" name="{field}" value="na" autocomplete="off"{selected}>N/A\n'
            '      </label>'
        )

    def submission_page(self):
        """ The submission's page, as the teacher sees it. """
        return self.client.get(reverse('quests:submission', args=[self.submission.pk]))

    def test_widget__na_first_and_not_chosen_while_awaiting_approval(self):
        """ Each competency's controls start with N/A, unchosen, ahead of the levels; the default level
        is still the one chosen """
        response = self.submission_page()

        content = response.content.decode()
        self.assertIn(self.na_button(self.thinking_field), content)
        self.assertLess(content.index(self.na_button(self.thinking_field)), content.index(f'name="{self.thinking_field}" value="1"'))
        self.assertContains(response, f'<input type="radio" name="{self.thinking_field}" value="4" autocomplete="off" checked>')

    def test_widget__na_chosen_on_an_approved_submission_with_no_level(self):
        """ Once approved, a competency the submission has no level in shows N/A chosen, and one it has
        a level in shows that level """
        self.post_decision('approve_button', **{self.thinking_field: NOT_APPLICABLE})
        self.submission.refresh_from_db()

        response = self.submission_page()

        self.assertContains(response, self.na_button(self.thinking_field, checked=True))
        self.assertContains(response, self.na_button(self.communicating_field))
        self.assertContains(response, f'<input type="radio" name="{self.communicating_field}" value="3" autocomplete="off" checked>')
