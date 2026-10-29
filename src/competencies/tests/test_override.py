import csv
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.db.models.deletion import ProtectedError
from django.template.defaultfilters import date as date_filter
from django.urls import reverse
from django.utils import timezone

from model_bakery import baker

from competencies.models import Competency, CompetencyAssessment, CompetencyOverride, ProficiencyLevel
from competencies.tests.test_approval import set_competencies_flag
from competencies.tests.test_matrix import CompetencyMatrixMixin
from competencies.tests.test_profile_views import StudentCompetenciesMixin
from hackerspace_online.tests.utils import ByteDeckTenantTestCase

User = get_user_model()

EMG, DEV, PRF, EXT = ProficiencyLevel.EMERGING, ProficiencyLevel.DEVELOPING, ProficiencyLevel.PROFICIENT, ProficiencyLevel.EXTENDING


class CompetencyOverrideModelTest(ByteDeckTenantTestCase):
    """ Tests for the CompetencyOverride model and its in_force queryset. """

    def setUp(self):
        """ Creates a teacher, a student and a competency. """
        self.teacher = baker.make(User, is_staff=True)
        self.student = baker.make(User, username="override_student")
        self.thinking = baker.make(Competency, name="Critical Thinking")

    def override(self, level, user=None, competency=None, minutes_ago=0):
        """ Records an override by the teacher (a clearing, with no level), stamped minutes ago.

        Returns:
            CompetencyOverride: the saved record.
        """
        override = CompetencyOverride.objects.create(
            user=user or self.student, competency=competency or self.thinking, level=level, set_by=self.teacher,
        )
        CompetencyOverride.objects.filter(pk=override.pk).update(timestamp=timezone.now() - timedelta(minutes=minutes_ago))
        return override

    def test_str__set_and_cleared(self):
        """ A record says what it set the level to, or that it cleared it """
        self.assertEqual(str(self.override(PRF)), "override_student: Critical Thinking set to Proficient")
        self.assertEqual(str(self.override(None)), "override_student: Critical Thinking cleared")

    def test_in_force__the_latest_record_per_student_and_competency(self):
        """ The override in force is each student's latest record for each competency, whatever order they
        were recorded in """
        latest = self.override(EMG, minutes_ago=5)
        self.override(EXT, minutes_ago=30)
        other_competency = self.override(PRF, competency=baker.make(Competency))
        other_student = self.override(DEV, user=baker.make(User))

        self.assertCountEqual(CompetencyOverride.objects.in_force(), [latest, other_competency, other_student])

    def test_in_force__a_clearing_leaves_none(self):
        """ When the latest record cleared the override, none is in force, though an earlier one set a level """
        self.override(EXT, minutes_ago=10)
        self.override(None, minutes_ago=5)

        self.assertFalse(CompetencyOverride.objects.in_force().exists())

    def test_in_force__timestamp_ties_go_to_the_one_recorded_last(self):
        """ Two records stamped the same moment resolve to the one recorded last """
        earlier = self.override(DEV)
        later = self.override(PRF)
        CompetencyOverride.objects.filter(pk__in=[earlier.pk, later.pk]).update(timestamp=timezone.now())

        self.assertEqual(list(CompetencyOverride.objects.in_force()), [later])

    def test_competency_delete__protected_by_an_override(self):
        """ A competency with a level set can be deactivated but not deleted, as with evidence """
        self.override(PRF)

        with self.assertRaises(ProtectedError):
            self.thinking.delete()


class CompetencyOverrideViewTest(StudentCompetenciesMixin, ByteDeckTenantTestCase):
    """ Tests for CompetencyOverrideView, where staff set or clear a student's level in a competency. """

    def setUp(self):
        """ The student is assessed Developing in "Choose a design opportunity", and the teacher signed in. """
        super().setUp()
        self.assess(self.defining, DEV, minutes_ago=60)
        self.client.force_login(self.teacher)

    def override_url(self, competency=None, student=None):
        """ The override page's URL for a student (this class's by default) and competency ("Choose a
        design opportunity" by default). """
        return reverse('competencies:override', args=[(student or self.student).pk, (competency or self.defining).pk])

    def row_url(self, competency=None):
        """ The competency's row on the student's competencies page, in the course's tab. """
        pane = f"course-pane-{self.registration.pk}"
        return f"{self.summary_url()}?course={pane}#{pane}-competency-{(competency or self.defining).pk}"

    def override(self, level, note=""):
        """ Records an override of "Choose a design opportunity" by the teacher.

        Returns:
            CompetencyOverride: the saved record.
        """
        return CompetencyOverride.objects.create(user=self.student, competency=self.defining, level=level, note=note, set_by=self.teacher)

    def test_get__the_evidence_and_no_override_yet(self):
        """ With no override, the page shows the level worked out from the evidence and how, that no
        teacher has set one, a form starting on no override with the deck's labels, and an empty history """
        response = self.client.get(self.override_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<strong>Grace Hopper</strong>'s level in <strong")
        self.assertContains(response, "ADST 9: Applied Design - Defining: Choose a design opportunity</strong>")
        self.assertContains(response, (
            'Worked out from the evidence (the level of its most recent assessment):\n    '
            '<span class="label competency-code competency-level competency-level-2">DEV</span> Developing'
        ))
        self.assertContains(response, "none, so the level worked out from the evidence stands")
        self.assertContains(response, '<option value="" selected>No override: the level worked out from the evidence</option>')
        self.assertContains(response, '<option value="4">Nailed It</option>')
        self.assertContains(response, "No teacher has set Grace's level in this competency yet.")
        self.assertContains(response, f'<a href="{self.row_url()}" role="button" class="btn btn-default">Cancel</a>')

    def test_get__the_override_in_force_and_the_history(self):
        """ With overrides recorded, the page shows the one in force (by whom, when and why), the form
        starts on it, and the history lists every record newest first, including a clearing """
        self.override(EXT, note="Strong portfolio")
        self.override(None, note="Changed my mind")
        latest = self.override(PRF, note="Seen in class")

        response = self.client.get(self.override_url())

        content = response.content.decode()
        self.assertRegex(content, (
            r'(?s)Set by a teacher:\s*'
            r'<span class="label competency-code competency-level competency-level-3 competency-override">GOT</span> Got It,\s*'
            rf'by Ada Lovelace on {date_filter(timezone.localtime(latest.timestamp))}: Seen in class'
        ))
        self.assertContains(response, '<option value="3" selected>Got It</option>')
        self.assertRegex(content, (
            r'(?s)<th>When</th>.*?Ada Lovelace.*?competency-level-3">Got It</span></td>\s*<td>Seen in class</td>'
            r'.*?<td>Cleared</td>\s*<td>Changed my mind</td>'
            r'.*?competency-level-4">Nailed It</span></td>\s*<td>Strong portfolio</td>'
        ))

    def test_get__not_yet_assessed_and_a_teacher_since_removed(self):
        """ A competency the student hasn't been assessed in shows n/a from the evidence, and an override by
        a teacher whose account is gone says so; with no course of the student's showing the competency,
        Cancel returns to their competencies page """
        elsewhere = baker.make(Competency, course="Math 9", name="Reason")
        CompetencyOverride.objects.create(user=self.student, competency=elsewhere, level=EMG, set_by=None)

        response = self.client.get(self.override_url(elsewhere))

        self.assertContains(response, '<span class="label competency-code label-default">n/a</span> Not yet assessed')
        self.assertContains(response, "by a teacher no longer on this deck on")
        self.assertContains(response, "<td>A teacher no longer on this deck</td>")
        pane = "course-pane-math-9"
        self.assertContains(response, f'<a href="{self.summary_url()}?course={pane}#{pane}-competency-{elsewhere.pk}" role="button"')

        CompetencyOverride.objects.all().delete()
        response = self.client.get(self.override_url(elsewhere))
        self.assertContains(response, f'<a href="{self.summary_url()}" role="button" class="btn btn-default">Cancel</a>')

    def test_post__sets_the_level(self):
        """ Saving a level records it with the note, by the teacher, and returns to the competency's row on
        the student's competencies page, where it is now their current level """
        response = self.client.post(self.override_url(), {'level': EXT, 'note': "Strong portfolio"})

        self.assertRedirects(response, self.row_url(), fetch_redirect_response=False)
        override = CompetencyOverride.objects.get()
        self.assertEqual(
            (override.user, override.competency, override.level, override.note, override.set_by),
            (self.student, self.defining, EXT, "Strong portfolio", self.teacher),
        )
        self.assertEqual(
            [str(m) for m in get_messages(response.wsgi_request)], ["Set Grace Hopper's level in Choose a design opportunity to Nailed It."],
        )
        self.assertContains(self.client.get(self.summary_url()), 'competency-level-4 competency-override"')

    def test_post__clears_the_override(self):
        """ Saving no level with an override in force records the clearing, so the evidence's level stands again """
        self.override(EXT)

        response = self.client.post(self.override_url(), {'level': '', 'note': "Back to the evidence"})

        self.assertRedirects(response, self.row_url(), fetch_redirect_response=False)
        cleared = CompetencyOverride.objects.order_by('-pk').first()
        self.assertEqual((cleared.level, cleared.note, cleared.set_by), (None, "Back to the evidence", self.teacher))
        self.assertFalse(CompetencyOverride.objects.in_force().exists())
        self.assertEqual(
            [str(m) for m in get_messages(response.wsgi_request)],
            ["Cleared the override of Choose a design opportunity: the level worked out from the evidence stands."],
        )

    def test_post__clearing_with_none_in_force_records_nothing(self):
        """ Saving no level when no override is in force records nothing, and says so """
        response = self.client.post(self.override_url(), {'level': '', 'note': ''})

        self.assertRedirects(response, self.row_url(), fetch_redirect_response=False)
        self.assertFalse(CompetencyOverride.objects.exists())
        self.assertEqual([str(m) for m in get_messages(response.wsgi_request)], ["There was no override to clear."])

    def test_post__an_unknown_level_is_refused(self):
        """ A level off the Proficiency Scale is a form error, and records nothing """
        response = self.client.post(self.override_url(), {'level': 9})

        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'level', "Select a valid choice. 9 is not one of the available choices.")
        self.assertFalse(CompetencyOverride.objects.exists())

    def test_access__staff_only_and_only_with_the_flag_on(self):
        """ Students get the 403 page, anonymous users are sent to log in, an unknown student or
        competency is not found, and with competencies off the page doesn't exist """
        self.client.force_login(self.student)
        self.assertEqual(self.client.get(self.override_url()).status_code, 403)
        self.assertEqual(self.client.post(self.override_url(), {'level': EXT}).status_code, 403)
        self.assertFalse(CompetencyOverride.objects.exists())

        self.client.logout()
        self.assertRedirects(self.client.get(self.override_url()), f"{reverse('account_login')}?next={self.override_url()}")

        self.client.force_login(self.teacher)
        self.assertEqual(self.client.get(reverse('competencies:override', args=[0, self.defining.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('competencies:override', args=[self.student.pk, 0])).status_code, 404)

        set_competencies_flag(False)
        self.assertEqual(self.client.get(self.override_url()).status_code, 404)


class OverrideMarkedTest(StudentCompetenciesMixin, ByteDeckTenantTestCase):
    """ An override shows as one on the student's competencies page: outlined, titled with who set it and
    when (and the note, for staff), and counted in the course's level. """

    def setUp(self):
        """ The student is assessed Emerging in "Choose a design opportunity", which a teacher has overridden
        to Nailed It. """
        super().setUp()
        self.assess(self.defining, EMG, minutes_ago=60)
        self.override = CompetencyOverride.objects.create(
            user=self.student, competency=self.defining, level=EXT, note="Strong portfolio", set_by=self.teacher,
        )

    def test_summary__the_override_is_outlined_and_counts(self):
        """ The student sees the override outlined in place of the evidence's level, titled with who set it
        and when but not the note, without the staff button, and counted in the average, which the
        explanation says """
        self.client.force_login(self.student)

        response = self.client.get(self.summary_url())

        when = date_filter(timezone.localtime(self.override.timestamp))
        self.assertContains(response, (
            '<span class="label competency-code competency-level competency-level-4 competency-override"\n'
            f'                    title="Nailed It: set by Ada Lovelace on {when}">NAI</span>'
        ))
        self.assertNotContains(response, "Strong portfolio")
        self.assertNotContains(response, "/competencies/override/")
        self.assertContains(response, "Where your teacher has set your level in a competency (outlined below), that level counts instead.")
        self.assertContains(response, "Your average is 4 / 3 = <strong>1.33</strong> out of 4.")

    def test_summary__staff_see_the_note(self):
        """ Staff also see the override's note in its title """
        self.client.force_login(self.teacher)

        response = self.client.get(self.summary_url())

        when = date_filter(timezone.localtime(self.override.timestamp))
        self.assertContains(response, f"set by Ada Lovelace on {when}: Strong portfolio\">NAI</span>")

    def test_summary__no_override_no_explanation(self):
        """ A course with no level overridden doesn't mention overrides in its explanation """
        self.override.delete()
        self.client.force_login(self.student)

        response = self.client.get(self.summary_url())

        self.assertNotContains(response, "Where your teacher has set your level")
        self.assertNotContains(response, "competency-override")


class OverrideInTheMatrixTest(CompetencyMatrixMixin, ByteDeckTenantTestCase):
    """ An override shows as one in the staff competency matrix and its CSV. """

    def test_matrix__an_override_is_outlined_and_marked_in_the_csv(self):
        """ An overridden cell is outlined and titled with who set it, the key explains the outline, and the
        CSV marks the level "(override)" """
        CompetencyAssessment.objects.create(user=self.zed, competency=self.defining, level=EMG)
        override = CompetencyOverride.objects.create(user=self.zed, competency=self.making, level=PRF, set_by=self.teacher)
        self.client.force_login(self.teacher)

        response = self.client.get(self.matrix_url())

        self.assertContains(response, 'competency-override">&nbsp;</span> Outlined: set by a teacher, in place of the evidence')
        when = date_filter(timezone.localtime(override.timestamp))
        self.assertContains(response, (
            'class="label competency-code competency-level competency-level-3 competency-override"\n'
            f'              title="Got It: Use materials safely (set by {self.teacher.profile.preferred_full_name()} on {when})">GOT</a>'
        ))
        self.assertContains(response, 'title="Emerging: Choose a design opportunity">EMG</a>')

        response = self.client.get(self.matrix_url(course=self.course.pk, format='csv'))
        header, adams, zed = list(csv.reader(io.StringIO(response.content.decode())))
        self.assertEqual(zed[5:], ['Emerging', 'Got It (override)'])
