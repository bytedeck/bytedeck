from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse

from model_bakery import baker

from comments.models import Comment
from competencies.forms import competency_level_field_name
from competencies.models import Competency, CompetencyAssessment, ProficiencyLevel, QuestCompetency
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from quest_manager.views import lock_is_approved
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
    auto-approval in the complete view), and commenting on an approved one records the levels
    changed; returning, skipping and commenting on an unapproved one record nothing. """

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
        """ Returning, commenting on or skipping a submission that isn't approved records no
        competency evidence """
        self.post_decision('return_button')
        self.post_decision('comment_button', comment_text='Keep going', **{competency_level_field_name(self.thinking.pk): ProficiencyLevel.EMERGING})
        self.post_decision('skip_button')

        self.assertFalse(CompetencyAssessment.objects.exists())

    def test_approve__again_after_a_return_replaces_the_levels(self):
        """ A submission approved, returned and approved again keeps only its latest level in each
        competency: the new approval replaces the earlier one for that quest """
        self.post_decision('approve_button')
        self.post_decision('return_button')
        self.post_decision('approve_button', **{competency_level_field_name(self.thinking.pk): ProficiencyLevel.PROFICIENT})

        self.assertEqual(self.recorded(self.submission), {
            self.thinking: ProficiencyLevel.PROFICIENT,
            self.communicating: ProficiencyLevel.PROFICIENT,
        })
        self.assertEqual(CompetencyAssessment.objects.count(), 2)

    def test_approve__again_starts_on_the_earlier_levels(self):
        """ Approving again with no levels posted (a quick approval) keeps the levels the submission
        already had, rather than resetting them to the defaults """
        self.post_decision('approve_button', **{competency_level_field_name(self.communicating.pk): ProficiencyLevel.EMERGING})
        self.post_decision('return_button')
        self.post_decision('approve_button')

        newest = CompetencyAssessment.objects.filter(competency=self.communicating).order_by('-timestamp', '-pk').first()
        self.assertEqual(newest.level, ProficiencyLevel.EMERGING)

    def test_comment__on_an_approved_submission_records_the_changed_levels(self):
        """ Commenting on an approved submission re-rates it: each level the teacher changed replaces
        the one it had (as the student's newest evidence), the others stay, and the comment lists only
        the changed ones (#2955) """
        self.post_decision('approve_button')
        unchanged = CompetencyAssessment.objects.get(competency=self.communicating)

        response = self.post_decision('comment_button', comment_text='On reflection', **{
            competency_level_field_name(self.thinking.pk): ProficiencyLevel.DEVELOPING,
            competency_level_field_name(self.communicating.pk): ProficiencyLevel.PROFICIENT,
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.recorded(self.submission), {
            self.thinking: ProficiencyLevel.DEVELOPING,
            self.communicating: ProficiencyLevel.PROFICIENT,
        })
        self.assertEqual(CompetencyAssessment.objects.count(), 2)
        self.assertEqual(CompetencyAssessment.objects.get(competency=self.communicating), unchanged)
        rerated = CompetencyAssessment.objects.get(competency=self.thinking)
        self.assertEqual(rerated.assessed_by, self.teacher)
        self.assertEqual(CompetencyAssessment.objects.filter(user=self.student).order_by('-timestamp', '-pk').first(), rerated)
        text = self.approval_comment()
        self.assertIn('On reflection', text)
        self.assertIn('<span title="Thinking: Critical Thinking">Critical Thinking</span>: <b>Developing</b>', text)
        self.assertNotIn('Communicating', text)

    def test_comment__with_the_levels_unchanged_records_nothing(self):
        """ A comment that leaves every level as it was records nothing and lists no levels """
        self.post_decision('approve_button', **{competency_level_field_name(self.thinking.pk): ProficiencyLevel.DEVELOPING})
        before = set(CompetencyAssessment.objects.values_list('pk', flat=True))

        self.post_decision('comment_button', comment_text='Thanks', **{competency_level_field_name(self.thinking.pk): ProficiencyLevel.DEVELOPING})

        self.assertEqual(set(CompetencyAssessment.objects.values_list('pk', flat=True)), before)
        self.assertNotIn('Competencies:', self.approval_comment())

    def test_comment__a_changed_level_alone_is_something_to_send(self):
        """ A comment with no text whose only content is a changed level is sent, as the levels alone;
        with nothing changed either, it is refused as before """
        self.post_decision('approve_button')
        comments = Comment.objects.count()

        response = self.post_decision('comment_button')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Write a comment or attach a file, then press Comment.")
        self.assertEqual(Comment.objects.count(), comments)

        response = self.post_decision('comment_button', **{competency_level_field_name(self.thinking.pk): ProficiencyLevel.PROFICIENT})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.approval_comment().split('<ul>')[0], '<p>Competencies:</p>')
        self.assertEqual(self.recorded(self.submission)[self.thinking], ProficiencyLevel.PROFICIENT)

    def test_comment__with_the_flag_off_records_no_levels(self):
        """ With competencies turned off after a submission was approved, a level posted with a comment
        is ignored: nothing is recorded, and a level alone is not something to send """
        self.post_decision('approve_button')
        before = set(CompetencyAssessment.objects.values_list('pk', flat=True))
        set_competencies_flag(False)
        changed = {competency_level_field_name(self.thinking.pk): ProficiencyLevel.EMERGING}

        response = self.post_decision('comment_button', **changed)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Write a comment or attach a file, then press Comment.")

        self.post_decision('comment_button', comment_text='Later', **changed)
        self.assertEqual(set(CompetencyAssessment.objects.values_list('pk', flat=True)), before)
        self.assertNotIn('Competencies:', self.approval_comment())

    def test_comment__a_return_committing_first_leaves_the_levels(self):
        """ When the submission is returned after this request loaded it as approved, the locked recheck
        sees the return and the comment records no levels """
        self.post_decision('approve_button')
        stale = QuestSubmission.objects.get(pk=self.submission.pk)  # loaded while still approved
        self.post_decision('return_button')  # the other request gets there first

        with patch('quest_manager.views.ApproveView.get_submission', return_value=stale):
            self.post_decision('comment_button', comment_text='Hmm', **{competency_level_field_name(self.thinking.pk): ProficiencyLevel.EMERGING})

        self.assertEqual(self.recorded(self.submission)[self.thinking], ProficiencyLevel.EXTENDING)

    def test_approve__a_repeated_approval_records_nothing_more(self):
        """ A second Approve on a submission that is already approved (a double-click) doesn't
        record a second set of assessments """
        self.post_decision('approve_button')
        self.post_decision('approve_button')

        self.assertEqual(CompetencyAssessment.objects.count(), 2)

    def test_approve__a_concurrent_approval_records_nothing_more(self):
        """ When another request approves the submission after this one loaded it (two Approve
        clicks handled at once), the locked recheck sees the approval and records nothing more """
        stale = QuestSubmission.objects.get(pk=self.submission.pk)  # loaded while still unapproved
        self.post_decision('approve_button')  # the other request gets there first

        with patch('quest_manager.views.ApproveView.get_submission', return_value=stale):
            self.post_decision('approve_button')

        self.assertEqual(CompetencyAssessment.objects.count(), 2)

    def test_lock_is_approved__reads_the_database_for_any_submission(self):
        """ lock_is_approved reads the row, not the in-memory submission, and finds a submission
        the default manager leaves out (one of an archived quest) """
        archived = self.make_submission(quest=baker.make(Quest, archived=True))
        stale = QuestSubmission.objects.get(pk=self.submission.pk)
        QuestSubmission.objects.filter(pk=self.submission.pk).update(is_approved=True)

        with transaction.atomic():
            self.assertFalse(lock_is_approved(archived))
            self.assertTrue(lock_is_approved(stale))

    def test_approve__records_nothing_when_disabled_or_without_competencies(self):
        """ No evidence is recorded with the flag off, nor for a quest with no competencies """
        self.post_decision('approve_button', submission=self.make_submission(quest=baker.make(Quest)))
        set_competencies_flag(False)
        self.post_decision('approve_button')

        self.assertFalse(CompetencyAssessment.objects.exists())

    def approval_comment(self):
        """ The text of the latest comment on this test's submission. """
        return Comment.objects.filter(target_object_id=self.submission.pk).order_by('-pk').first().text

    def test_approve__comment_lists_the_recorded_levels(self):
        """ The comment that approves the submission lists each competency with the level recorded,
        in the deck's labels, after the teacher's own text """
        self.post_decision('approve_button', comment_text='Nice work', **{
            competency_level_field_name(self.thinking.pk): ProficiencyLevel.DEVELOPING,
        })

        text = self.approval_comment()
        self.assertIn('Nice work', text)
        self.assertIn('<p>Competencies:</p>', text)
        self.assertIn('<span title="Thinking: Critical Thinking">Critical Thinking</span>: <b>Developing</b>', text)
        self.assertIn('<span title="Communication: Communicating">Communicating</span>: <b>Proficient</b>', text)
        self.assertNotIn('Retired Competency', text)

    def test_approve__comment_cuts_a_long_competency_name_short(self):
        """ A long competency name in the approving comment is cut short, in full in its title """
        long_name = "Critically analyze and prioritize competing factors to meet community needs"
        QuestCompetency.objects.create(quest=self.quest, competency=baker.make(Competency, name=long_name, category="Ideating"))

        self.post_decision('approve_button')

        self.assertIn(f'<span title="Ideating: {long_name}">{long_name[:49]}\u2026</span>', self.approval_comment())

    def test_return_and_repeated_approval__comments_list_no_levels(self):
        """ Returning records nothing, so its comment lists no levels; nor does a second Approve on a
        submission already approved, which records nothing more """
        self.post_decision('return_button')
        self.assertNotIn('Competencies:', self.approval_comment())

        self.post_decision('approve_button')
        self.post_decision('approve_button')
        self.assertNotIn('Competencies:', self.approval_comment())

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

    def test_complete__auto_approved_quest_records_once(self):
        """ Completing an already auto-approved submission again (a duplicate submit) doesn't record
        its competencies a second time """
        auto_quest = baker.make(Quest, xp=5, verification_required=False)
        QuestCompetency.objects.create(quest=auto_quest, competency=self.thinking)
        submission = self.make_submission(quest=auto_quest, is_completed=False, draft_comment=baker.make(Comment, text='draft'))
        self.client.force_login(self.student)
        url = reverse('quests:complete', args=[submission.pk])

        self.client.post(url, data={'complete': True, 'comment_text': 'done'})
        submission.refresh_from_db()
        submission.draft_comment = baker.make(Comment, text='draft again')
        submission.save()
        self.client.post(url, data={'complete': True, 'comment_text': 'done again'})

        self.assertEqual(CompetencyAssessment.objects.count(), 1)

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

    def test_levels__nudge_shows_from_the_start_when_a_default_is_the_lowest(self):
        """ The nudge renders visible when a competency's default level is already the lowest,
        and hidden otherwise, without waiting for a level to change """
        url = reverse('quests:submission', args=[self.submission.pk])
        self.assertContains(self.client.get(url), 'class="help-block text-warning competency-lowest-nudge hidden"')

        QuestCompetency.objects.filter(quest=self.quest, competency=self.communicating).update(default_level=ProficiencyLevel.EMERGING)

        self.assertContains(self.client.get(url), 'class="help-block text-warning competency-lowest-nudge"')

    def test_levels__keep_the_posted_choice_when_the_form_comes_back_with_errors(self):
        """ When an approval doesn't validate (here, a badge that can't be granted) and the
        submission page comes back with the errors, each level stays on what the teacher posted,
        so pressing Approve again records their choice rather than the default """
        thinking_field = competency_level_field_name(self.thinking.pk)

        response = self.client.post(reverse('quests:approve', args=[self.submission.pk]), data={
            'approve_button': True, 'awards': [999999], thinking_field: ProficiencyLevel.DEVELOPING,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'<input type="radio" name="{thinking_field}" value="2" autocomplete="off" checked>')
        self.assertContains(response, f'<input type="radio" name="{thinking_field}" value="4" autocomplete="off">')
        self.assertFalse(CompetencyAssessment.objects.exists())

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

    def test_levels__absent_when_disabled_or_without_competencies(self):
        """ No controls with the flag off, nor for a quest without competencies """
        bare = self.make_submission(quest=baker.make(Quest))
        self.assertNotContains(self.client.get(reverse('quests:submission', args=[bare.pk])), 'competency-approval-levels')

        set_competencies_flag(False)
        for url in (reverse('quests:submitted_all'), reverse('quests:submission', args=[self.submission.pk])):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertNotContains(response, 'competency-approval-levels')
                self.assertNotContains(response, 'competencies/js/approval-levels.js')

    def test_levels__on_an_approved_submission_start_on_its_levels(self):
        """ An approved submission's form still has the controls, so a comment can re-rate it: they
        start on the levels it has, say a comment records the changes, and drop the nudge about
        returning it (#2955) """
        thinking_field = competency_level_field_name(self.thinking.pk)
        self.client.post(reverse('quests:approve', args=[self.submission.pk]), data={
            'approve_button': True, 'comment_text': '', thinking_field: ProficiencyLevel.DEVELOPING,
        })

        response = self.client.get(reverse('quests:submission', args=[self.submission.pk]))

        self.assertContains(response, 'class="competency-approval-levels"')
        self.assertContains(response, '(any you change are recorded when you comment)')
        self.assertContains(response, f'<input type="radio" name="{thinking_field}" value="2" autocomplete="off" checked>')
        self.assertContains(response, f'<input type="radio" name="{thinking_field}" value="4" autocomplete="off">')
        self.assertNotContains(response, "usually means the quest isn't complete yet")

    def test_approved_tab__fetches_the_submissions_levels_for_the_whole_page(self):
        """ The approved tab's rows start on each submission's levels, fetched for the page at once """
        self.client.post(reverse('quests:approve', args=[self.submission.pk]), data={'approve_button': True, 'comment_text': ''})

        response = self.client.get(reverse('quests:approved_all'))

        tab = next(t for t in response.context['tab_list'] if t['active'])
        submission = next(s for s in tab['submissions'] if s.pk == self.submission.pk)
        self.assertEqual(submission.competency_levels, {
            self.thinking.pk: ProficiencyLevel.EXTENDING, self.communicating.pk: ProficiencyLevel.PROFICIENT,
        })
