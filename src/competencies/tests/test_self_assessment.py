from django.contrib.auth import get_user_model
from django.urls import reverse

from model_bakery import baker

from comments.models import Comment
from competencies.assessments import posted_self_assessments, record_self_assessments, submission_levels, submission_self_levels
from competencies.forms import competency_level_field_name, self_assessment_field_name
from competencies.models import CompetencyAssessment, ProficiencyLevel, QuestCompetency
from competencies.tests.test_approval import ApprovalTestMixin, set_competencies_flag
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest

User = get_user_model()

EMG, DEV, PRF, EXT = ProficiencyLevel.EMERGING, ProficiencyLevel.DEVELOPING, ProficiencyLevel.PROFICIENT, ProficiencyLevel.EXTENDING


class SelfAssessmentMixin(ApprovalTestMixin):
    """ The approval fixtures (a quest with "Critical Thinking", default Extending, "Communicating" and a
    deactivated competency), with the quest asking for a self-assessment and competencies on. """

    def setUp(self):
        """ Turn competencies on and have the quest ask for a self-assessment. """
        set_competencies_flag(True)
        self.quest.competency_self_assessment = True
        self.quest.save()

    def hand_in(self, submission, **levels):
        """ The student hands a submission in, with the self-assessment levels given (by competency).

        Args:
            submission (QuestSubmission): the student's submission, with a draft comment.
            **levels: POST data, e.g. ``{self_assessment_field_name(pk): 3}``.

        Returns:
            HttpResponse: the complete view's response.
        """
        self.client.force_login(self.student)
        return self.client.post(
            reverse('quests:complete', args=[submission.pk]), data={'complete': True, 'comment_text': 'Done', **levels},
        )

    def draft(self, quest=None):
        """ A submission of the quest by the student, not yet handed in, with a draft comment. """
        return self.make_submission(quest=quest, is_completed=False, draft_comment=baker.make(Comment, text='draft'))

    def self_assessed(self, submission):
        """ The student's self-assessments of a submission, as {competency: level}. """
        return {
            assessment.competency: assessment.level
            for assessment in CompetencyAssessment.objects.self_assessments().filter(source_object_id=submission.pk)
        }


class SelfAssessmentQuerySetTest(SelfAssessmentMixin, ByteDeckTenantTestCase):
    """ Tests for CompetencyAssessmentQuerySet's teacher_evidence and self_assessments. """

    def test_querysets__a_self_assessment_is_not_evidence(self):
        """ An assessment by the student themself is a self-assessment; a teacher's, or a system one with
        no assessor, is evidence """
        mine = CompetencyAssessment.objects.create(user=self.student, competency=self.thinking, level=PRF, assessed_by=self.student)
        teachers = CompetencyAssessment.objects.create(user=self.student, competency=self.thinking, level=DEV, assessed_by=self.teacher)
        systems = CompetencyAssessment.objects.create(user=self.student, competency=self.thinking, level=EXT)

        self.assertEqual(list(CompetencyAssessment.objects.self_assessments()), [mine])
        self.assertCountEqual(CompetencyAssessment.objects.teacher_evidence(), [teachers, systems])


class SelfAssessmentRecordingTest(SelfAssessmentMixin, ByteDeckTenantTestCase):
    """ Handing in a quest that asks for a self-assessment records the levels the student chose. """

    def test_hand_in__records_the_levels_chosen(self):
        """ Each level chosen is recorded as the student's assessment of themself, sourced from the
        submission; one left on Skip isn't, and the deactivated competency is never asked about """
        submission = self.draft()

        response = self.hand_in(submission, **{
            self_assessment_field_name(self.thinking.pk): PRF,
            self_assessment_field_name(self.communicating.pk): '',
            self_assessment_field_name(self.retired.pk): EXT,
        })

        self.assertEqual(response.status_code, 302)
        assessment = CompetencyAssessment.objects.get()
        self.assertEqual(
            (assessment.user, assessment.competency, assessment.level, assessment.assessed_by, assessment.source_object),
            (self.student, self.thinking, PRF, self.student, submission),
        )

    def test_hand_in__lists_the_self_assessment_in_the_comment(self):
        """ The comment the quest is handed in with lists each level chosen, under the student's text, in
        the deck's labels """
        set_competencies_flag(True, competency_label_level_3="Got It")
        submission = self.draft()

        self.hand_in(submission, **{self_assessment_field_name(self.thinking.pk): PRF})

        text = Comment.objects.filter(target_object_id=submission.pk).order_by('-pk').first().text
        self.assertIn('<p>Done</p>', text)
        self.assertIn('<li><b>Self-assessment of Critical Thinking: Got It</b></li>', text)
        self.assertNotIn('Communicating', text)

    def test_hand_in__a_level_off_the_scale_is_ignored(self):
        """ Anything posted that isn't a level (a hand-made request) records nothing """
        submission = self.draft()

        self.hand_in(submission, **{self_assessment_field_name(self.thinking.pk): 9, self_assessment_field_name(self.communicating.pk): 'x'})

        self.assertFalse(CompetencyAssessment.objects.exists())

    def test_hand_in__nothing_when_not_asked_or_disabled(self):
        """ A quest that doesn't ask for a self-assessment records none, whatever is posted, nor does a
        deck with competencies turned off """
        self.quest.competency_self_assessment = False
        self.quest.save()
        self.hand_in(self.draft(), **{self_assessment_field_name(self.thinking.pk): PRF})
        self.assertFalse(CompetencyAssessment.objects.exists())

        self.quest.competency_self_assessment = True
        self.quest.save()
        set_competencies_flag(False)
        self.hand_in(self.draft(), **{self_assessment_field_name(self.thinking.pk): PRF})
        self.assertFalse(CompetencyAssessment.objects.exists())

    def test_hand_in_again__replaces_the_earlier_self_assessment(self):
        """ Handing a returned submission in again replaces the student's earlier self-assessment of each
        competency they choose a level for, keeps the rest, and leaves the teacher's levels alone """
        submission = self.draft()
        self.hand_in(submission, **{
            self_assessment_field_name(self.thinking.pk): DEV, self_assessment_field_name(self.communicating.pk): EMG,
        })
        self.client.force_login(self.teacher)
        self.client.post(reverse('quests:approve', args=[submission.pk]), data={'approve_button': True, 'comment_text': ''})
        self.client.post(reverse('quests:approve', args=[submission.pk]), data={'return_button': True, 'comment_text': 'Again'})
        submission.refresh_from_db()
        submission.draft_comment = baker.make(Comment, text='draft again')
        submission.save()

        self.hand_in(submission, **{self_assessment_field_name(self.thinking.pk): EXT})

        self.assertEqual(self.self_assessed(submission), {self.thinking: EXT, self.communicating: EMG})
        self.assertEqual(submission_levels(submission), {self.thinking.pk: EXT, self.communicating.pk: PRF})

    def test_hand_in__an_auto_approved_quest_records_both(self):
        """ A quest that needs no approval records its default levels, system-assessed, and the student's
        self-assessment beside them """
        auto_quest = baker.make(Quest, xp=5, verification_required=False, competency_self_assessment=True)
        QuestCompetency.objects.create(quest=auto_quest, competency=self.thinking, default_level=DEV)
        submission = self.draft(quest=auto_quest)

        self.hand_in(submission, **{self_assessment_field_name(self.thinking.pk): EXT})

        self.assertEqual(submission_levels(submission), {self.thinking.pk: DEV})
        self.assertEqual(submission_self_levels(submission), {self.thinking.pk: EXT})

    def test_comment__records_no_self_assessment(self):
        """ Commenting on a handed-in submission (rather than handing it in) records no self-assessment """
        submission = self.make_submission(is_approved=True)
        self.client.force_login(self.student)

        self.client.post(reverse('quests:complete', args=[submission.pk]), data={
            'comment': True, 'comment_text': 'Another thought', self_assessment_field_name(self.thinking.pk): PRF,
        })

        self.assertFalse(CompetencyAssessment.objects.exists())

    def test_record_self_assessments__nothing_chosen_records_nothing(self):
        """ With no level chosen, nothing is recorded """
        submission = self.make_submission()

        self.assertEqual(record_self_assessments(submission, posted_self_assessments(submission, {})), [])
        self.assertFalse(CompetencyAssessment.objects.exists())


class TeacherLevelsIgnoreSelfAssessmentTest(SelfAssessmentMixin, ByteDeckTenantTestCase):
    """ A self-assessment of a submission is kept apart from the teacher's levels for it. """

    def setUp(self):
        """ The student self-assessed Critical Thinking as Emerging on handing the submission in. """
        super().setUp()
        self.submission = self.make_submission()
        CompetencyAssessment.objects.create(
            user=self.student, competency=self.thinking, level=EMG, assessed_by=self.student, source_object=self.submission,
        )

    def test_approve__starts_on_the_defaults_and_keeps_the_self_assessment(self):
        """ The approval form starts on the link's default, not the student's level, and approving records
        the teacher's levels without replacing the self-assessment """
        self.assertEqual(submission_levels(self.submission), {})
        self.client.force_login(self.teacher)

        self.client.post(reverse('quests:approve', args=[self.submission.pk]), data={'approve_button': True, 'comment_text': ''})

        self.assertEqual(submission_levels(self.submission), {self.thinking.pk: EXT, self.communicating.pk: PRF})
        self.assertEqual(self.self_assessed(self.submission), {self.thinking: EMG})

    def test_comment__re_rating_keeps_the_self_assessment(self):
        """ Re-rating an approved submission by commenting replaces only the teacher's level """
        self.client.force_login(self.teacher)
        url = reverse('quests:approve', args=[self.submission.pk])
        self.client.post(url, data={'approve_button': True, 'comment_text': ''})

        self.client.post(url, data={'comment_button': True, 'comment_text': 'Better', competency_level_field_name(self.thinking.pk): DEV})

        self.assertEqual(submission_levels(self.submission)[self.thinking.pk], DEV)
        self.assertEqual(self.self_assessed(self.submission), {self.thinking: EMG})


class SelfAssessmentFormTest(SelfAssessmentMixin, ByteDeckTenantTestCase):
    """ The student's self-assessment controls on their submission page. """

    def submission_page(self, submission, user=None):
        """ The submission page, as the student (or another user).

        Returns:
            HttpResponse: the page.
        """
        self.client.force_login(user or self.student)
        return self.client.get(reverse('quests:submission', args=[submission.pk]))

    def test_submission_page__a_control_per_competency_starting_on_skip(self):
        """ The student's form has a self-assessment control per active competency of the quest, in the
        deck's labels, starting on Skip """
        set_competencies_flag(True, competency_label_level_4="Nailed It")

        response = self.submission_page(self.draft())

        content = response.content.decode()
        self.assertContains(response, '<strong>Your self-assessment</strong>')
        self.assertContains(response, "it doesn't count toward your level.")
        self.assertRegex(content, (
            r'(?s)<span class="competency-approval-name">Communicating</span>.*?'
            r'<label class="btn btn-default active">\s*'
            rf'<input type="radio" name="{self_assessment_field_name(self.communicating.pk)}" value="" autocomplete="off" checked>Skip'
            r'.*?<label class="btn btn-default competency-level competency-level-4">\s*'
            rf'<input type="radio" name="{self_assessment_field_name(self.communicating.pk)}" value="4" autocomplete="off">Nailed It'
        ))
        self.assertContains(response, f'name="{self_assessment_field_name(self.thinking.pk)}"', count=5)
        self.assertNotContains(response, self_assessment_field_name(self.retired.pk))

    def test_submission_page__starts_on_the_earlier_self_assessment(self):
        """ A submission returned to the student starts on the levels they chose when they handed it in """
        submission = self.draft()
        CompetencyAssessment.objects.create(
            user=self.student, competency=self.thinking, level=DEV, assessed_by=self.student, source_object=submission,
        )

        response = self.submission_page(submission)

        self.assertRegex(response.content.decode(), (
            r'<label class="btn btn-default competency-level competency-level-2 active">\s*'
            rf'<input type="radio" name="{self_assessment_field_name(self.thinking.pk)}" value="2" autocomplete="off" checked>'
        ))

    def test_submission_page__re_rendered_on_the_levels_posted(self):
        """ When the hand-in is refused for a problem with the form, the page comes back on the levels the
        student chose """
        self.quest.xp_can_be_entered_by_students = True
        self.quest.save()
        submission = self.draft()

        response = self.hand_in(submission, **{self_assessment_field_name(self.thinking.pk): PRF})

        self.assertEqual(response.status_code, 200)
        self.assertRegex(response.content.decode(), (
            r'<label class="btn btn-default competency-level competency-level-3 active">\s*'
            rf'<input type="radio" name="{self_assessment_field_name(self.thinking.pk)}" value="3" autocomplete="off" checked>'
        ))
        self.assertFalse(CompetencyAssessment.objects.exists())

    def test_submission_page__no_controls_unless_asked(self):
        """ No controls when the quest doesn't ask, the deck has competencies off, the submission is
        approved, or a teacher views it """
        submission = self.draft()
        self.assertNotContains(self.submission_page(submission, user=self.teacher), 'Your self-assessment')
        self.assertNotContains(self.submission_page(self.make_submission(is_approved=True)), 'Your self-assessment')

        self.quest.competency_self_assessment = False
        self.quest.save()
        self.assertNotContains(self.submission_page(submission), 'Your self-assessment')

        self.quest.competency_self_assessment = True
        self.quest.save()
        set_competencies_flag(False)
        self.assertNotContains(self.submission_page(submission), 'Your self-assessment')
