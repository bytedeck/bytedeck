import csv
import io

from django.contrib.auth import get_user_model
from django.db import connection
from django.template.defaultfilters import date as date_filter
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from model_bakery import baker

from comments.models import Comment
from competencies.assessments import posted_self_assessments, record_self_assessments, submission_levels, submission_self_levels
from competencies.forms import competency_level_field_name, self_assessment_field_name
from competencies.models import CompetencyAssessment, ProficiencyLevel, QuestCompetency, RollupStrategy
from competencies.rollup import current_levels, evidence_levels, latest_self_assessments
from competencies.summaries import course_competencies
from competencies.tests.test_approval import ApprovalTestMixin, set_competencies_flag
from competencies.tests.test_profile_views import StudentCompetenciesMixin, own_query_count
from competencies.tests.test_rollup import set_rollup
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

    def test_hand_in__the_comment_names_the_course(self):
        """ A competency with a course is named with it in the comment, since courses can share a
        competency's wording """
        self.thinking.course = "ADST 9"
        self.thinking.save()
        submission = self.draft()

        self.hand_in(submission, **{self_assessment_field_name(self.thinking.pk): EXT})

        text = Comment.objects.filter(target_object_id=submission.pk).order_by('-pk').first().text
        self.assertIn('<li><b>Self-assessment of Critical Thinking (ADST 9): Extending</b></li>', text)

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
        competency they choose a level for, clears one they switch to Skip, and leaves the teacher's
        levels alone """
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

        self.hand_in(submission, **{
            self_assessment_field_name(self.thinking.pk): EXT, self_assessment_field_name(self.communicating.pk): '',
        })

        self.assertEqual(self.self_assessed(submission), {self.thinking: EXT})
        self.assertEqual(submission_levels(submission), {self.thinking.pk: EXT, self.communicating.pk: PRF})
        text = Comment.objects.filter(target_object_id=submission.pk).order_by('-pk').first().text
        self.assertIn('Self-assessment of Critical Thinking: Extending', text)
        self.assertNotIn('Self-assessment of Communicating', text)

    def test_hand_in_again__a_competency_not_posted_keeps_its_level(self):
        """ A competency missing from the POST altogether (a hand-made request; the form always posts
        every one) keeps its earlier self-assessment """
        submission = self.draft()
        self.hand_in(submission, **{
            self_assessment_field_name(self.thinking.pk): DEV, self_assessment_field_name(self.communicating.pk): EMG,
        })
        submission.draft_comment = baker.make(Comment, text='draft again')
        submission.save()

        self.hand_in(submission, **{self_assessment_field_name(self.thinking.pk): EXT})

        self.assertEqual(self.self_assessed(submission), {self.thinking: EXT, self.communicating: EMG})

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
            r'(?s)<span class="competency-approval-name" title="Communication: Communicating">Communicating</span>.*?'
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


class SelfAssessmentNotCountedTest(SelfAssessmentMixin, ByteDeckTenantTestCase):
    """ Self-assessments never count toward a current level, by any strategy, and are read apart. """

    def setUp(self):
        """ The student is assessed Developing by the teacher, then self-assesses Extending. """
        super().setUp()
        CompetencyAssessment.objects.create(user=self.student, competency=self.thinking, level=DEV, assessed_by=self.teacher)
        self.mine = CompetencyAssessment.objects.create(user=self.student, competency=self.thinking, level=EXT, assessed_by=self.student)

    def test_current_levels__ignore_self_assessments_by_any_strategy(self):
        """ The current level is the teacher's, whether by the most recent, the most common or the highest """
        for strategy in RollupStrategy.values:
            with self.subTest(strategy=strategy):
                set_rollup(strategy)
                levels, overrides = current_levels(user=self.student)
                self.assertEqual(levels[self.student.pk], {self.thinking.pk: DEV})
                self.assertEqual(evidence_levels(user=self.student)[self.student.pk], {self.thinking.pk: DEV})

    def test_current_levels__a_self_assessment_alone_is_no_level(self):
        """ A competency the student has only self-assessed has no current level """
        CompetencyAssessment.objects.create(user=self.student, competency=self.communicating, level=EXT, assessed_by=self.student)

        levels, overrides = current_levels(user=self.student)

        self.assertNotIn(self.communicating.pk, levels[self.student.pk])

    def test_latest_self_assessments__the_latest_per_student_and_competency(self):
        """ Each student's latest self-assessment of each competency, not the teacher's, filtered like the
        current levels, in one query """
        later = CompetencyAssessment.objects.create(user=self.student, competency=self.thinking, level=PRF, assessed_by=self.student)
        CompetencyAssessment.objects.filter(pk__in=[self.mine.pk, later.pk]).update(timestamp=self.mine.timestamp)
        other = baker.make(User)
        theirs = CompetencyAssessment.objects.create(user=other, competency=self.communicating, level=EMG, assessed_by=other)

        with CaptureQueriesContext(connection) as queries:
            latest = latest_self_assessments(user_id__in=[self.student.pk, other.pk])

        self.assertEqual(own_query_count(queries), 1)
        self.assertEqual(latest[self.student.pk], {self.thinking.pk: later})
        self.assertEqual(latest[other.pk], {self.communicating.pk: theirs})
        self.assertEqual(latest_self_assessments(user=self.student, competency=self.communicating)[self.student.pk], {})


class SelfAssessmentShownTest(StudentCompetenciesMixin, ByteDeckTenantTestCase):
    """ A self-assessment shows hollow beside the teacher's levels on the competencies page and the matrix,
    and as context on the approval form. """

    def setUp(self):
        """ The student is assessed Developing in "Choose a design opportunity" by the teacher, then
        self-assesses Nailed It on the same quest, and Got It in the Core "Collaborating". """
        super().setUp()
        self.brainstorm = self.submission("Brainstorm")
        self.assess(self.defining, DEV, minutes_ago=30, source=self.brainstorm, assessed_by=self.teacher)
        self.mine = self.assess(self.defining, EXT, minutes_ago=20, source=self.brainstorm, assessed_by=self.student)
        self.core = self.assess(self.collaborating, PRF, minutes_ago=10, source=self.brainstorm, assessed_by=self.student)

    def test_course_competencies__self_assessments_beside_and_not_counted(self):
        """ Each course carries the student's latest self-assessments; the average counts only the teacher's
        level, and a set the student has only self-assessed in (Core) shows, with no level """
        adst, core = course_competencies(self.student)

        self.assertEqual(adst.self_assessed, {self.defining.pk: self.mine, self.collaborating.pk: self.core})
        self.assertEqual(adst.course_levels, [DEV])
        self.assertEqual((core.label, core.course_levels, core.level), ("Core", [], 0))

    def test_summary__hollow_chips_beside_the_teachers(self):
        """ The competencies page shows the self-assessment hollow beside the current level and among the
        chips (titled as one), leaves it out of the levels over time, and the explanation says so """
        self.assess(self.defining, PRF, minutes_ago=10, source=self.submission("Prototype"), assessed_by=self.teacher)
        self.client.force_login(self.student)

        response = self.client.get(self.summary_url())

        content = response.content.decode()
        when = date_filter(timezone.localtime(CompetencyAssessment.objects.get(pk=self.mine.pk).timestamp))
        self.assertRegex(content, (
            rf'(?s)<tr id="course-pane-{self.registration.pk}-competency-{self.defining.pk}">.*?'
            r'<td class="competency-summary-current">\s*'
            r'<span class="label competency-code competency-level competency-level-3" title="Got It">GOT</span>\s*'
            r'<span class="label competency-code competency-level competency-level-4 competency-self"\s*'
            rf'title="Self-assessed: Nailed It, {when}">NAI</span>\s*</td>\s*'
            r'<td class="competency-summary-history">\s*<span class="competency-history" role="img"\s*'
            r'title="Level over time, oldest first: Developing, Got It"'
            r'.*?class="label competency-code competency-level competency-level-4 competency-self"\s*'
            rf'title="Self-assessed: Nailed It: Brainstorm, {when}">NAI</a>'
        ))
        self.assertContains(response, (
            "Hollow chips are your own self-assessments: they show beside your teacher's levels and don't count toward them."
        ))

    def test_summary__no_self_assessment_no_mention(self):
        """ With no self-assessments, there's no hollow chip and the explanation doesn't mention them """
        CompetencyAssessment.objects.self_assessments().delete()
        self.client.force_login(self.student)

        response = self.client.get(self.summary_url())

        self.assertNotContains(response, 'competency-self')
        self.assertNotContains(response, 'Hollow chips are your own self-assessments')

    def test_matrix__hollow_chip_beside_the_teachers(self):
        """ The matrix shows the self-assessment hollow beside the student's level in the cell, the key
        explains it, and the CSV keeps to the teacher's levels """
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('competencies:matrix'))

        when = date_filter(timezone.localtime(CompetencyAssessment.objects.get(pk=self.mine.pk).timestamp))
        self.assertContains(response, "competency-self\">&nbsp;</span> Hollow: the student's self-assessment, not counted")
        self.assertContains(response, (
            '<span class="label competency-code competency-level competency-level-4 competency-self"\n'
            f'              title="Self-assessed: Nailed It: Choose a design opportunity, {when}">NAI</span>'
        ))
        rows = list(csv.reader(io.StringIO(self.client.get(reverse('competencies:matrix') + '?format=csv').content.decode())))
        self.assertEqual(rows[1][5:], ['Developing', 'n/a', 'n/a'])

    def test_approval_form__shows_the_self_assessment(self):
        """ The approval form shows the student's self-assessment of the submission beside its competency,
        hollow and in full, and nothing beside one they didn't self-assess """
        QuestCompetency.objects.create(quest=self.brainstorm.quest, competency=self.defining)
        QuestCompetency.objects.create(quest=self.brainstorm.quest, competency=self.making)
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('quests:submission', args=[self.brainstorm.pk]))

        self.assertContains(response, (
            '<span class="competency-approval-name" title="ADST 9: Applied Design - Defining: Choose a design opportunity">'
            'Choose a design opportunity <small class="text-muted">(ADST 9)</small>\n'
            '      <span class="label competency-level competency-level-4 competency-self" '
            'title="The student\'s self-assessment, not counted">Self: Nailed It</span></span>'
        ))
        self.assertContains(response, (
            '<span class="competency-approval-name" title="ADST 9: Applied Design - Making: Use materials safely">'
            'Use materials safely <small class="text-muted">(ADST 9)</small></span>'
        ))

    def test_approvals_tab__self_assessments_fetched_for_the_page(self):
        """ The approvals page fetches every row's self-assessments at once, as it does their levels """
        self.brainstorm.is_completed = True
        self.brainstorm.semester = self.semester
        self.brainstorm.save()
        QuestCompetency.objects.create(quest=self.brainstorm.quest, competency=self.defining)
        self.client.force_login(self.teacher)

        response = self.client.get(reverse('quests:submitted_all'))

        tab = next(t for t in response.context['tab_list'] if t['active'])
        submission = next(s for s in tab['submissions'] if s.pk == self.brainstorm.pk)
        self.assertEqual(submission.competency_self_levels, {self.defining.pk: EXT, self.collaborating.pk: PRF})
        self.assertContains(response, 'Self: Nailed It')
