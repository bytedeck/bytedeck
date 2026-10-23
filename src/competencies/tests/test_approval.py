from django.contrib.auth import get_user_model
from django.urls import reverse

from model_bakery import baker

from comments.models import Comment
from competencies.forms import competency_level_field_name
from competencies.models import Competency, CompetencyAssessment, ProficiencyLevel, QuestCompetency
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


def set_competencies_flag(enabled, **labels):
    """ Set the competencies feature flag, and any scale labels, on the test deck.

    Args:
        enabled (bool): the flag's value.
        **labels: SiteConfig competency_label_level_* values to set.
    """
    config = SiteConfig.get()
    config.enable_competencies = enabled
    for field, value in labels.items():
        setattr(config, field, value)
    config.full_clean()
    config.save()


class ApprovalTestMixin:
    """ A teacher, a student in the active semester, and a quest with two active competencies
    (one defaulting to Extending, one to Proficient) and a deactivated one. """

    @classmethod
    def setUpTestData(cls):
        """ Create the users, the quest and its competency links. """
        cls.teacher = User.objects.create_user('approval_teacher', is_staff=True)
        cls.student = User.objects.create_user('approval_student')
        cls.semester = SiteConfig.get().active_semester
        baker.make('courses.CourseStudent', user=cls.student, course=baker.make('courses.Course'), semester=cls.semester)

        cls.quest = baker.make(Quest, name="Competency Quest", xp=5)
        cls.thinking = baker.make(Competency, name="Critical Thinking", category="Thinking")
        cls.communicating = baker.make(Competency, name="Communicating", category="Communication")
        cls.retired = baker.make(Competency, name="Retired Competency", active=False)
        QuestCompetency.objects.create(quest=cls.quest, competency=cls.thinking, default_level=ProficiencyLevel.EXTENDING)
        QuestCompetency.objects.create(quest=cls.quest, competency=cls.communicating)
        QuestCompetency.objects.create(quest=cls.quest, competency=cls.retired)

    def make_submission(self, quest=None, **kwargs):
        """ A submission of the quest by the student, handed in and awaiting approval.

        Args:
            quest (Quest, optional): the quest; this class's quest by default.
            **kwargs: QuestSubmission field overrides.

        Returns:
            QuestSubmission: the submission.
        """
        fields = {'is_completed': True, 'semester': self.semester, **kwargs}
        return baker.make(QuestSubmission, quest=quest or self.quest, user=self.student, **fields)

    def recorded(self, submission):
        """ The assessments recorded for a submission, as {competency: level}.

        Args:
            submission (QuestSubmission): the assessments' source.

        Returns:
            dict: competency to level, one entry per assessment.
        """
        return {
            assessment.competency: assessment.level
            for assessment in CompetencyAssessment.objects.filter(source_object_id=submission.pk)
        }


class ApprovalAssessmentTest(ApprovalTestMixin, ByteDeckTenantTestCase):
    """ Approving a submission records its quest's competency evidence (ApproveView and the
    auto-approval in the complete view); returning, commenting and skipping record nothing. """

    def setUp(self):
        """ Turn competencies on and sign the teacher in. """
        set_competencies_flag(True)
        self.client.force_login(self.teacher)
        self.submission = self.make_submission()

    def post_decision(self, button, submission=None, **data):
        """ Post a decision on a submission from the approvals page's quick reply form.

        Args:
            button (str): the button pressed, e.g. 'approve_button'.
            submission (QuestSubmission, optional): this test's submission by default.
            **data: further POST data, e.g. competency levels.

        Returns:
            HttpResponse: the view's response.
        """
        submission = submission or self.submission
        return self.client.post(
            reverse('quests:approve', args=[submission.pk]),
            data={button: True, 'comment_text': '', **data},
        )

    def test_approve__records_the_default_levels(self):
        """ Approving with the levels as they were pre-selected records each active competency at
        its default level, by the approving teacher, sourced from the submission """
        response = self.post_decision('approve_button')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.recorded(self.submission), {
            self.thinking: ProficiencyLevel.EXTENDING,
            self.communicating: ProficiencyLevel.PROFICIENT,
        })
        assessment = CompetencyAssessment.objects.get(competency=self.thinking)
        self.assertEqual(assessment.user, self.student)
        self.assertEqual(assessment.assessed_by, self.teacher)
        self.assertEqual(assessment.source_object, self.submission)

    def test_approve__records_adjusted_levels(self):
        """ A level the teacher changed before approving is the one recorded """
        self.post_decision('approve_button', **{competency_level_field_name(self.thinking.pk): ProficiencyLevel.DEVELOPING})

        self.assertEqual(self.recorded(self.submission), {
            self.thinking: ProficiencyLevel.DEVELOPING,
            self.communicating: ProficiencyLevel.PROFICIENT,
        })

    def test_approve__an_invalid_posted_level_falls_back_to_the_default(self):
        """ A posted level outside the scale (or not a number) records the default instead """
        self.post_decision('approve_button', **{
            competency_level_field_name(self.thinking.pk): '9',
            competency_level_field_name(self.communicating.pk): 'high',
        })

        self.assertEqual(self.recorded(self.submission), {
            self.thinking: ProficiencyLevel.EXTENDING,
            self.communicating: ProficiencyLevel.PROFICIENT,
        })

    def test_approve__full_submission_form_records_levels(self):
        """ Approving from the full submission page's staff form (here with a badge granted, which
        routes to SubmissionFormStaff) records the posted levels too """
        badge = baker.make('badges.Badge', xp=0, badge_type=baker.make('badges.BadgeType'))

        response = self.post_decision('approve_button', awards=[badge.pk], **{
            competency_level_field_name(self.communicating.pk): ProficiencyLevel.EMERGING,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.recorded(self.submission), {
            self.thinking: ProficiencyLevel.EXTENDING,
            self.communicating: ProficiencyLevel.EMERGING,
        })

    def test_return_comment_and_skip__record_nothing(self):
        """ Returning, commenting on or skipping a submission records no competency evidence """
        self.post_decision('return_button')
        self.post_decision('comment_button', comment_text='Keep going')
        self.post_decision('skip_button')

        self.assertFalse(CompetencyAssessment.objects.exists())

    def test_approve__again_after_a_return_adds_new_assessments(self):
        """ A submission approved, returned and approved again records a second set of assessments
        rather than replacing the first: the history is kept """
        self.post_decision('approve_button')
        self.post_decision('return_button')
        self.post_decision('approve_button', **{competency_level_field_name(self.thinking.pk): ProficiencyLevel.PROFICIENT})

        self.assertEqual(
            sorted(CompetencyAssessment.objects.filter(competency=self.thinking).values_list('level', flat=True)),
            [ProficiencyLevel.PROFICIENT, ProficiencyLevel.EXTENDING],
        )
        self.assertEqual(CompetencyAssessment.objects.count(), 4)

    def test_approve__records_nothing_when_disabled_or_without_competencies(self):
        """ No evidence is recorded with the flag off, nor for a quest with no competencies """
        self.post_decision('approve_button', submission=self.make_submission(quest=baker.make(Quest)))
        set_competencies_flag(False)
        self.post_decision('approve_button')

        self.assertFalse(CompetencyAssessment.objects.exists())

    def test_complete__auto_approved_quest_records_defaults_without_an_assessor(self):
        """ Handing in a quest that needs no approval records its competencies at their default
        levels, system-assessed (no assessor), since no teacher approves it """
        auto_quest = baker.make(Quest, xp=5, verification_required=False)
        QuestCompetency.objects.create(quest=auto_quest, competency=self.thinking, default_level=ProficiencyLevel.DEVELOPING)
        submission = self.make_submission(quest=auto_quest, is_completed=False, draft_comment=baker.make(Comment, text='draft'))
        self.client.force_login(self.student)

        self.client.post(reverse('quests:complete', args=[submission.pk]), data={'complete': True, 'comment_text': 'done'})

        submission.refresh_from_db()
        self.assertTrue(submission.is_approved)
        assessment = CompetencyAssessment.objects.get()
        self.assertEqual((assessment.competency, assessment.level, assessment.assessed_by), (self.thinking, ProficiencyLevel.DEVELOPING, None))
        self.assertEqual(assessment.source_object, submission)

    def test_complete__quest_needing_approval_records_nothing_yet(self):
        """ Handing in a quest that needs a teacher's approval records nothing until it is approved """
        submission = self.make_submission(is_completed=False, draft_comment=baker.make(Comment, text='draft'))
        self.client.force_login(self.student)

        self.client.post(reverse('quests:complete', args=[submission.pk]), data={'complete': True, 'comment_text': 'done'})

        submission.refresh_from_db()
        self.assertTrue(submission.is_completed)
        self.assertFalse(CompetencyAssessment.objects.exists())


class ApprovalLevelsWidgetTest(ApprovalTestMixin, ByteDeckTenantTestCase):
    """ The competency level controls on the approvals page and the full submission page. """

    def setUp(self):
        """ Turn competencies on (with a custom lowest label) and sign the teacher in. """
        set_competencies_flag(True, competency_label_level_1="Beginning")
        self.client.force_login(self.teacher)
        self.submission = self.make_submission()

    def assertShowsLevels(self, response):
        """ Assert a page shows the submission's level controls, pre-selected to the defaults.

        Args:
            response (HttpResponse): the rendered page.

        Raises:
            AssertionError: if the controls, their defaults, the nudge or its script are missing,
                or the deactivated competency is offered.
        """
        thinking_field = competency_level_field_name(self.thinking.pk)
        self.assertContains(response, 'class="competency-approval-levels"')
        self.assertContains(response, f'<input type="radio" name="{thinking_field}" value="4" autocomplete="off" checked>')
        self.assertContains(response, f'<input type="radio" name="{thinking_field}" value="3" autocomplete="off">')
        self.assertContains(response, "Beginning usually means the quest isn't complete yet")
        self.assertContains(response, 'competencies/js/approval-levels.js')
        self.assertNotContains(response, competency_level_field_name(self.retired.pk))

    def test_approvals_tab__shows_the_levels_preselected(self):
        """ Each submission's quick reply form on the approvals page carries its level controls """
        self.assertShowsLevels(self.client.get(reverse('quests:submitted_all')))

    def test_approvals_tab__fetches_the_quests_links_for_the_whole_page(self):
        """ The quests' competency links are prefetched for the page, not queried per row """
        response = self.client.get(reverse('quests:submitted_all'))

        tab = next(t for t in response.context['tab_list'] if t['active'])
        submission = next(s for s in tab['submissions'] if s.pk == self.submission.pk)
        self.assertIn('quest_competencies', submission.quest._prefetched_objects_cache)

    def test_submission_page__shows_the_levels_preselected(self):
        """ The full submission page's staff form carries the level controls """
        self.assertShowsLevels(self.client.get(reverse('quests:submission', args=[self.submission.pk])))

    def test_levels__absent_when_disabled_without_competencies_or_approved(self):
        """ No controls with the flag off, for a quest without competencies, or once approved """
        bare = self.make_submission(quest=baker.make(Quest))
        approved = self.make_submission(is_approved=True)
        for submission in (bare, approved):
            with self.subTest(submission=submission.pk):
                self.assertNotContains(self.client.get(reverse('quests:submission', args=[submission.pk])), 'competency-approval-levels')

        set_competencies_flag(False)
        for url in (reverse('quests:submitted_all'), reverse('quests:submission', args=[self.submission.pk])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotContains(response, 'competency-approval-levels')
                self.assertNotContains(response, 'competencies/js/approval-levels.js')
