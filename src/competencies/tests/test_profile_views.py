from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from model_bakery import baker

from competencies.models import Competency, CompetencyAssessment, ProficiencyLevel
from competencies.tests.test_approval import set_competencies_flag
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission

User = get_user_model()


def own_query_count(queries):
    """ The queries captured, less django-tenants' per-cursor search path setting (not ours).

    Args:
        queries (CaptureQueriesContext): the captured queries.

    Returns:
        int: how many of them are queries of ours.
    """
    return len([query for query in queries.captured_queries if not query['sql'].startswith('SET search_path')])


class CompetencyEvidenceMixin:
    """ A teacher, a student, and competencies from a course to assess the student on, on a deck
    with competencies enabled. """

    def setUp(self):
        """ Creates the users and competencies, and enables competencies with custom labels. """
        set_competencies_flag(True, competency_label_level_3="Got It", competency_label_level_4="Nailed It")
        self.teacher = User.objects.create_user('evidence_teacher', first_name="Ada", last_name="Lovelace", is_staff=True)
        self.teacher.profile.alias = "Ms. L"
        self.teacher.profile.save()
        self.student = User.objects.create_user('evidence_student', first_name="Grace", last_name="Hopper")
        self.thinking = baker.make(Competency, course="ADST 9", category="Applied Design - Defining", name="Choose a design opportunity")
        self.making = baker.make(Competency, course="ADST 9", category="Applied Design - Making", name="Use materials safely")
        self.core = baker.make(Competency, course="Core", category="Communication", name="Collaborating")

    def assess(self, competency, level, minutes_ago, source=None, assessed_by=None, user=None):
        """ Records an assessment of the student, stamped the given number of minutes ago.

        Returns:
            CompetencyAssessment: the saved assessment.
        """
        assessment = CompetencyAssessment.objects.create(
            user=user or self.student, competency=competency, level=level, source_object=source, assessed_by=assessed_by,
        )
        CompetencyAssessment.objects.filter(pk=assessment.pk).update(timestamp=timezone.now() - timedelta(minutes=minutes_ago))
        return assessment

    def submission(self, quest_name, **quest_fields):
        """ A submission by the student of a new quest with the given name.

        Returns:
            QuestSubmission: the submission.
        """
        return baker.make(QuestSubmission, user=self.student, quest=baker.make(Quest, name=quest_name, **quest_fields))

    def evidence_url(self, competency, student=None):
        """ The evidence page's URL for a student (this class's by default) and competency. """
        return reverse('competencies:evidence', args=[(student or self.student).pk, competency.pk])


class ProfileCompetenciesTest(CompetencyEvidenceMixin, ByteDeckTenantTestCase):
    """ Tests for the Competencies panel on a student's profile (the profile_competencies tag). """

    def profile_url(self, user=None):
        """ The profile page's URL for a user (this class's student by default). """
        return reverse('profiles:profile_detail', args=[(user or self.student).profile.pk])

    def test_profile__shows_each_current_level_grouped_by_course_and_category(self):
        """ Each competency with evidence shows its most recent level in the deck's label and colour,
        under its course and category, linked to its evidence; competencies without evidence aren't listed """
        self.assess(self.thinking, ProficiencyLevel.DEVELOPING, minutes_ago=30)
        self.assess(self.thinking, ProficiencyLevel.EXTENDING, minutes_ago=5)
        self.assess(self.core, ProficiencyLevel.PROFICIENT, minutes_ago=10)
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        self.assertContains(response, '<h3 class="panel-title">Competencies</h3>')
        content = response.content.decode()
        self.assertRegex(content, (
            r'(?s)list-group-item-info">ADST 9: Applied Design - Defining</div>\s*'
            rf'<a href="{self.evidence_url(self.thinking)}" class="list-group-item list-group-item-packed competency-level-row" '
            r'title="ADST 9: Applied Design - Defining: Choose a design opportunity">\s*'
            r'<span class="competency-level-row-name">Choose a design opportunity</span>\s*'
            r'<span class="label competency-level competency-level-4">Nailed It</span>\s*</a>'
            r'.*list-group-item-info">Core: Communication</div>\s*'
            rf'<a href="{self.evidence_url(self.core)}".*?Collaborating</span>\s*<span[^>]*competency-level-3">Got It</span>'
        ))
        self.assertNotContains(response, "Use materials safely")
        self.assertNotContains(response, "Applied Design - Making")

    def test_profile__levels_take_the_same_queries_however_many_competencies(self):
        """ The panel adds no query per competency: a profile with four competencies assessed takes the
        same number of queries as one with a single competency assessed """
        self.assess(self.thinking, ProficiencyLevel.PROFICIENT, minutes_ago=1)
        self.client.force_login(self.teacher)
        self.client.get(self.profile_url())  # warm up per-request caches, such as the deck's SiteConfig

        with CaptureQueriesContext(connection) as one:
            self.client.get(self.profile_url())

        for competency in (self.making, self.core, baker.make(Competency)):
            self.assess(competency, ProficiencyLevel.DEVELOPING, minutes_ago=1)
        with CaptureQueriesContext(connection) as four:
            response = self.client.get(self.profile_url())

        self.assertEqual(response.content.decode().count('class="competency-level-row-name"'), 4)
        self.assertEqual(own_query_count(four), own_query_count(one))

    def test_profile__empty_state(self):
        """ A student with no evidence yet gets the panel saying so """
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        self.assertContains(response, '<h3 class="panel-title">Competencies</h3>')
        self.assertContains(response, '<div class="list-group-item">None yet.</div>', html=True)

    def test_profile__no_panel_when_disabled(self):
        """ With the flag off the profile has no Competencies panel, even for a student with evidence """
        self.assess(self.thinking, ProficiencyLevel.PROFICIENT, minutes_ago=1)
        set_competencies_flag(False)
        self.client.force_login(self.student)

        response = self.client.get(self.profile_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<h3 class="panel-title">Competencies</h3>')
        self.assertNotContains(response, "Choose a design opportunity")

    def test_profile__no_panel_on_a_staff_profile(self):
        """ Teachers aren't assessed, so their own profile has no Competencies panel """
        self.client.force_login(self.teacher)

        response = self.client.get(self.profile_url(self.teacher))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<h3 class="panel-title">Competencies</h3>')


class CompetencyEvidenceViewTest(CompetencyEvidenceMixin, ByteDeckTenantTestCase):
    """ Tests for CompetencyEvidenceView, the evidence behind a student's level in one competency. """

    def test_evidence__staff_see_each_assessment_linked_to_its_submission(self):
        """ Staff see every assessment of the competency, most recent first, each with its date, its quest
        linked to the submission, its level in the deck's label and colour, and who assessed it """
        first = self.submission("Brainstorm")
        second = self.submission("Prototype")
        self.assess(self.thinking, ProficiencyLevel.DEVELOPING, minutes_ago=60 * 24, source=first, assessed_by=self.teacher)
        self.assess(self.thinking, ProficiencyLevel.EXTENDING, minutes_ago=5, source=second)
        self.assess(self.core, ProficiencyLevel.EMERGING, minutes_ago=1, source=second)
        self.client.force_login(self.teacher)

        response = self.client.get(self.evidence_url(self.thinking))

        self.assertContains(response, '<h1 class="clearfix"><i class="fa fa-graduation-cap pull-right"></i>Choose a design opportunity</h1>')
        self.assertContains(response, "ADST 9: Applied Design - Defining")
        self.assertContains(response, f'Evidence for <a href="{self.student.profile.get_absolute_url()}">Grace Hopper</a>')
        self.assertContains(response, 'currently <span class="label competency-level competency-level-4">Nailed It</span>')
        content = response.content.decode()
        self.assertRegex(content, (
            rf'(?s)<a href="{second.get_absolute_url()}">Prototype</a>.*?competency-level-4">Nailed It</span>.*?Automatic'
            rf'.*<a href="{first.get_absolute_url()}">Brainstorm</a>.*?competency-level-2">Developing</span>.*?Ada Lovelace'
        ))
        self.assertEqual(content.count('<tr>') - 1, 2)  # two rows besides the header: the other competency's evidence isn't here

    def test_evidence__the_student_sees_quest_names_without_links(self):
        """ A student sees their own evidence, naming each quest without a link to the submission and
        each teacher by their alias """
        submission = self.submission("Brainstorm")
        self.assess(self.thinking, ProficiencyLevel.PROFICIENT, minutes_ago=5, source=submission, assessed_by=self.teacher)
        self.client.force_login(self.student)

        response = self.client.get(self.evidence_url(self.thinking))

        self.assertContains(response, "Brainstorm")
        self.assertNotContains(response, submission.get_absolute_url())
        self.assertContains(response, "Ms. L")
        self.assertNotContains(response, "Ada Lovelace")

    def test_evidence__names_the_quest_after_it_is_archived(self):
        """ Evidence from a quest since archived and unpublished still names it """
        submission = self.submission("Old Quest", archived=True, published=False)
        self.assess(self.thinking, ProficiencyLevel.PROFICIENT, minutes_ago=5, source=submission)
        self.client.force_login(self.teacher)

        self.assertContains(self.client.get(self.evidence_url(self.thinking)), f'<a href="{submission.get_absolute_url()}">Old Quest</a>')

    def test_evidence__a_deleted_quest_is_named_as_such(self):
        """ Evidence outlives its quest, and says the quest it came from was deleted """
        submission = self.submission("Gone Quest")
        self.assess(self.thinking, ProficiencyLevel.PROFICIENT, minutes_ago=5, source=submission)
        submission.quest.delete()
        self.client.force_login(self.teacher)

        response = self.client.get(self.evidence_url(self.thinking))

        self.assertContains(response, "<em>A deleted quest</em>", html=True)
        self.assertNotContains(response, "Gone Quest")

    def test_evidence__empty_state(self):
        """ A competency the student has no evidence for yet says so, with no current level """
        self.client.force_login(self.student)

        response = self.client.get(self.evidence_url(self.making))

        self.assertContains(response, '<tr><td colspan="4">None yet.</td></tr>', html=True)
        self.assertNotContains(response, "currently")

    def test_evidence__queries_dont_grow_with_the_evidence(self):
        """ Each assessment's submission, quest and teacher are fetched with the rest, not one by one """
        self.assess(self.thinking, ProficiencyLevel.PROFICIENT, minutes_ago=5, source=self.submission("Q1"), assessed_by=self.teacher)
        self.client.force_login(self.teacher)
        self.client.get(self.evidence_url(self.thinking))  # warm up per-request caches

        with CaptureQueriesContext(connection) as one:
            self.client.get(self.evidence_url(self.thinking))

        other_teacher = User.objects.create_user('other_teacher', is_staff=True)
        for minutes_ago, name in ((4, "Q2"), (3, "Q3"), (2, "Q4")):
            self.assess(self.thinking, ProficiencyLevel.EXTENDING, minutes_ago=minutes_ago, source=self.submission(name), assessed_by=other_teacher)
        with CaptureQueriesContext(connection) as four:
            response = self.client.get(self.evidence_url(self.thinking))

        self.assertContains(response, ">Q4</a>")
        self.assertEqual(own_query_count(four), own_query_count(one))

    def test_evidence__another_students_evidence_is_not_found(self):
        """ A student can't see another student's evidence: the page doesn't exist for them """
        other_student = User.objects.create_user('other_student')
        self.assess(self.thinking, ProficiencyLevel.PROFICIENT, minutes_ago=5, user=other_student)
        self.client.force_login(self.student)

        self.assertEqual(self.client.get(self.evidence_url(self.thinking, student=other_student)).status_code, 404)

    def test_evidence__anonymous_users_are_sent_to_log_in(self):
        """ The page needs a logged-in user """
        response = self.client.get(self.evidence_url(self.thinking))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('account_login'), response.url)

    def test_evidence__unknown_student_or_competency_is_not_found(self):
        """ A URL naming a student or competency that doesn't exist is a 404 """
        self.client.force_login(self.teacher)
        missing_pk = Competency.objects.order_by('-pk').first().pk + 1

        self.assertEqual(self.client.get(reverse('competencies:evidence', args=[self.student.pk, missing_pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('competencies:evidence', args=[0, self.thinking.pk])).status_code, 404)

    def test_evidence__not_found_when_disabled(self):
        """ With the flag off the page doesn't exist, even for staff """
        self.assess(self.thinking, ProficiencyLevel.PROFICIENT, minutes_ago=5)
        set_competencies_flag(False)
        self.client.force_login(self.teacher)

        self.assertEqual(self.client.get(self.evidence_url(self.thinking)).status_code, 404)
