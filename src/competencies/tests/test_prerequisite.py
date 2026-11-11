from unittest.mock import patch

from django.conf import settings
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.forms.models import model_to_dict
from django.template.loader import render_to_string
from django.urls import reverse

from model_bakery import baker

from badges.models import BadgeAssertion
from competencies.assessments import (
    queue_conditions_update, queue_conditions_update_for_everyone, record_approval_assessments, record_level_changes,
)
from competencies.forms import competency_level_field_name
from competencies.models import Competency, CompetencyAssessment, CompetencyOverride, ProficiencyLevel, QuestCompetency, RollupStrategy
from competencies.templatetags.competency_tags import competency_prereq_levels
from competencies.tests.test_approval import set_competencies_flag
from competencies.tests.test_rollup import set_rollup
from djcytoscape.models import CytoElement, CytoScape
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from prerequisites.forms import PrereqFormInline
from prerequisites.models import IsAPrereqMixin, Prereq
from prerequisites.tasks import update_quest_conditions_all_users, update_quest_conditions_for_user
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig
from utilities.widgets import GFKSelect2Widget

User = get_user_model()

EMG, DEV, PRF, EXT = ProficiencyLevel.EMERGING, ProficiencyLevel.DEVELOPING, ProficiencyLevel.PROFICIENT, ProficiencyLevel.EXTENDING


class CompetencyPrerequisiteMixin:
    """ A teacher, a student, a quest, and an ADST 9 competency, on a deck with competencies enabled
    and "Got It" for level 3. """

    def setUp(self):
        """ Creates the users, the quest and the competency. """
        set_competencies_flag(True, competency_label_level_3="Got It")
        self.teacher = User.objects.create_user('prereq_teacher', is_staff=True)
        self.student = User.objects.create_user('prereq_student')
        self.quest = baker.make(Quest, name="Advanced Design")
        self.defining = baker.make(Competency, course="ADST 9", category="Defining", name="Choose a design opportunity")

    def assess(self, level, assessed_by=None, competency=None):
        """ Records an assessment of the student, by the teacher unless another assessor is given.

        Returns:
            CompetencyAssessment: the saved assessment.
        """
        return CompetencyAssessment.objects.create(
            user=self.student, competency=competency or self.defining, level=level, assessed_by=assessed_by or self.teacher,
        )

    def require(self, level, invert=False, **extra):
        """ Gives the quest the prerequisite "the competency at this level or higher" (or NOT so).

        Returns:
            Prereq: the prerequisite.
        """
        return Prereq.objects.create(parent_object=self.quest, prereq_object=self.defining, prereq_count=level, prereq_invert=invert, **extra)

    def met(self):
        """ Whether the student meets all the quest's prerequisites. """
        return Prereq.objects.all_conditions_met(self.quest, self.student)


class CompetencyAsPrerequisiteTest(CompetencyPrerequisiteMixin, ByteDeckTenantTestCase):
    """ Tests for Competency.condition_met_as_prerequisite: the student's current level against the minimum. """

    def test_competency__is_a_registered_prerequisite_model(self):
        """ A competency is offered as a prerequisite like a quest or a badge """
        self.assertTrue(IsAPrereqMixin.model_is_registered(Competency))
        self.assertIn(Competency, IsAPrereqMixin.all_registered_model_classes())

    def test_condition_met__the_current_level_reaches_the_minimum(self):
        """ Met once the student's current level is the minimum or higher; no level is never met """
        self.assertFalse(self.defining.condition_met_as_prerequisite(self.student, EMG))

        self.assess(DEV)

        self.assertTrue(self.defining.condition_met_as_prerequisite(self.student, EMG))
        self.assertTrue(self.defining.condition_met_as_prerequisite(self.student, DEV))
        self.assertFalse(self.defining.condition_met_as_prerequisite(self.student, PRF))

    def test_condition_met__by_the_decks_roll_up_with_overrides_and_without_self_assessments(self):
        """ The current level is the roll-up's: the deck's strategy decides it, a teacher's override
        stands in for it, and a self-assessment never counts """
        self.assess(EXT)
        self.assess(EMG)
        self.assess(EXT, assessed_by=self.student)
        self.assertFalse(self.defining.condition_met_as_prerequisite(self.student, PRF))

        set_rollup(RollupStrategy.HIGHEST)
        self.assertTrue(self.defining.condition_met_as_prerequisite(self.student, PRF))

        set_rollup(RollupStrategy.MOST_RECENT)
        CompetencyOverride.objects.create(user=self.student, competency=self.defining, level=PRF, set_by=self.teacher)
        self.assertTrue(self.defining.condition_met_as_prerequisite(self.student, PRF))

    def test_quest__opens_as_the_level_lands(self):
        """ A quest needing "Got It in X" stays closed below it and opens once the student reaches it,
        in the conditions the available quests are worked out from """
        self.require(PRF)
        self.assess(DEV)
        self.assertFalse(self.met())
        self.assertNotIn(self.quest.pk, self.cached_ids())

        self.assess(PRF)
        self.assertTrue(self.met())
        self.assertIn(self.quest.pk, self.cached_ids())

    def cached_ids(self):
        """ The quests the student can start, by the conditions update. """
        update_quest_conditions_for_user(self.student.pk)
        from prerequisites.models import PrereqAllConditionsMet
        return PrereqAllConditionsMet.objects.get(user=self.student, model_name=Quest.get_model_name()).get_ids()

    def test_quest__not_and_or_and_combinations(self):
        """ A competency prerequisite combines like any other: NOT (below the level), OR (the level or a
        badge), and alongside another prerequisite (both needed) """
        not_prereq = self.require(PRF, invert=True)
        self.assertTrue(self.met())
        self.assess(PRF)
        self.assertFalse(self.met())
        not_prereq.delete()

        badge = baker.make('badges.Badge', name="Design Pass")
        Prereq.objects.create(parent_object=self.quest, prereq_object=self.defining, prereq_count=EXT, or_prereq_object=badge)
        self.assertFalse(self.met())
        BadgeAssertion.objects.create_assertion(self.student, badge)
        self.assertTrue(self.met())

        other = baker.make(Competency, course="ADST 9", name="Use materials safely")
        Prereq.objects.create(parent_object=self.quest, prereq_object=other, prereq_count=EMG)
        self.assertFalse(self.met())
        self.assess(EMG, competency=other)
        self.assertTrue(self.met())


class CompetencyPrerequisiteLabelTest(CompetencyPrerequisiteMixin, ByteDeckTenantTestCase):
    """ How a competency prerequisite reads: "Got It in ADST 9: ...", and among a form's choices. """

    def test_str__the_level_in_the_competency(self):
        """ A prerequisite names the competency's minimum level by the deck's labels, on either side,
        with NOT and OR as usual """
        prereq = self.require(PRF, or_prereq_object=self.defining, or_prereq_count=EXT, or_prereq_invert=True)

        self.assertEqual(
            str(prereq),
            "(competency) Got It in ADST 9: Defining: Choose a design opportunity OR NOT (competency) Extending in ADST 9: Defining: "
            "Choose a design opportunity",
        )

    def test_str__a_count_off_the_scale_and_a_deleted_competency(self):
        """ A count off the scale (made outside the form) reads as a numbered level, and a competency since
        deleted reads as None """
        prereq = self.require(7)
        self.assertEqual(str(prereq), "(competency) Level 7 in ADST 9: Defining: Choose a design opportunity")

        self.defining.delete()
        self.assertEqual(str(Prereq.objects.get(pk=prereq.pk)), "(competency) None")

    def test_choice_label__the_qualified_name_for_a_competency(self):
        """ The prerequisite search names a competency in full, and other elements by their names """
        widget = GFKSelect2Widget()

        self.assertEqual(widget.label_from_instance(self.defining), "ADST 9: Defining: Choose a design opportunity")
        self.assertEqual(widget.label_from_instance(self.quest), "Advanced Design")
        self.assertEqual(Competency.gfk_search_fields(), ["name__icontains", "course__icontains", "category__icontains"])

    def test_prereq_list__a_competency_is_listed_without_a_link(self):
        """ The quest's list of prerequisites names a competency prerequisite without a link (it has no
        page), and links a quest prerequisite as before """
        self.require(PRF)
        earlier = baker.make(Quest, name="Basics")
        Prereq.objects.create(parent_object=self.quest, prereq_object=earlier)

        html = render_to_string('prerequisites/current_prereq_list.html', {'object': self.quest})
        badge_html = render_to_string('badges/snippets/badge_popover_content.html', {'badge': self.badge_requiring_the_competency()})

        self.assertIn("<li>(competency) Got It in ADST 9: Defining: Choose a design opportunity</li>", html)
        self.assertIn(f"<li><a href='{earlier.get_absolute_url()}'>(quest) Basics</a></li>", html)
        self.assertIn("<li>(competency) Got It in ADST 9: Defining: Choose a design opportunity</li>", badge_html)

    def badge_requiring_the_competency(self):
        """ A badge with the competency at Got It as its prerequisite. """
        badge = baker.make('badges.Badge', name="Designer")
        Prereq.objects.create(parent_object=badge, prereq_object=self.defining, prereq_count=PRF)
        return badge


class CompetencyPrerequisiteFormTest(CompetencyPrerequisiteMixin, ByteDeckTenantTestCase):
    """ The advanced prerequisites form with a competency: its count is a level, offered by name. """

    def form(self, count, or_count=None, or_object=None):
        """ A prerequisite form row requiring the competency, optionally with an alternate.

        Returns:
            PrereqFormInline: the bound form.
        """
        from django.contrib.contenttypes.models import ContentType
        competency_type = ContentType.objects.get_for_model(Competency).pk
        data = {
            'prereq_object': f"{competency_type}-{self.defining.pk}", 'prereq_count': count,
            'or_prereq_count': 1 if or_count is None else or_count,
        }
        if or_object is not None:
            data['or_prereq_object'] = f"{ContentType.objects.get_for_model(or_object).pk}-{or_object.pk}"
        return PrereqFormInline(data=data, instance=Prereq(parent_object=self.quest))

    def test_clean__a_competencys_count_is_a_level(self):
        """ A competency's count must be a level on the scale, on either side; another element takes any count """
        self.assertTrue(self.form(PRF).is_valid(), self.form(PRF).errors)

        form = self.form(5)
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['prereq_count'], ["For a competency, the count is the minimum level: 1 (Emerging) to 4 (Extending)."])

        form = self.form(PRF, or_count=0, or_object=self.defining)
        self.assertFalse(form.is_valid())
        self.assertIn('or_prereq_count', form.errors)

        self.assertTrue(self.form(PRF, or_count=9, or_object=baker.make(Quest)).is_valid())

    def test_prereq_levels_tag__the_competency_type_and_levels(self):
        """ The form's level picker gets the competency content type and the deck's levels, Got It to start
        on, and nothing with competencies disabled """
        from django.contrib.contenttypes.models import ContentType

        self.assertEqual(competency_prereq_levels(), {
            'content_type_id': ContentType.objects.get_for_model(Competency).pk,
            'levels': [[1, "Emerging"], [2, "Developing"], [3, "Got It"], [4, "Extending"]],
            'default_level': PRF,
        })
        set_competencies_flag(False)
        self.assertIsNone(competency_prereq_levels())

    def test_advanced_form__the_level_picker_with_competencies_on(self):
        """ The quest's advanced prerequisites page loads the level picker and explains a competency's count,
        only with competencies enabled """
        self.client.force_login(self.teacher)
        url = reverse('quests:quest_prereqs_update', args=[self.quest.pk])

        response = self.client.get(url)
        self.assertContains(response, 'id="competency-prereq-levels"')
        self.assertContains(response, 'competencies/js/prereq-levels.js')
        self.assertContains(response, "For a competency, the count is the minimum level, chosen by name")

        set_competencies_flag(False)
        response = self.client.get(url)
        self.assertNotContains(response, 'competency-prereq-levels')
        self.assertNotContains(response, "For a competency")


class ConditionsUpdateTest(CompetencyPrerequisiteMixin, ByteDeckTenantTestCase):
    """ A new level queues the recalculation of which quests the student can start, when a prerequisite
    asks for a competency level. """

    def test_queue_conditions_update__only_with_a_competency_prerequisite(self):
        """ Nothing is queued while no prerequisite asks for a competency; one is once a prerequisite does,
        as the requirement or the alternate """
        with patch.object(update_quest_conditions_for_user, 'apply_async') as queued:
            queue_conditions_update(self.student.pk)
            queued.assert_not_called()

            alternate = Prereq.objects.create(parent_object=self.quest, prereq_object=baker.make(Quest), or_prereq_object=self.defining)
            queue_conditions_update(self.student.pk)
            queued.assert_called_once_with(args=[self.student.pk], queue='default')

            alternate.delete()
            self.require(PRF)
            queue_conditions_update(self.student.pk)
            self.assertEqual(queued.call_count, 2)

    def test_recording__approval_re_rating_and_overrides_queue_the_update(self):
        """ Approving a submission, re-rating it by comment and setting an override each queue the update
        once; recording nothing queues nothing """
        QuestCompetency.objects.create(quest=self.quest, competency=self.defining)
        submission = baker.make(QuestSubmission, quest=self.quest, user=self.student, is_completed=True, is_approved=True)

        with patch('competencies.assessments.queue_conditions_update') as queued:
            record_approval_assessments(submission, self.teacher)
            queued.assert_called_once_with(self.student.pk)

            record_level_changes(submission, self.teacher, {})
            self.assertEqual(queued.call_count, 1)
            record_level_changes(submission, self.teacher, {competency_level_field_name(self.defining.pk): EMG})
            self.assertEqual(queued.call_count, 2)

            record_approval_assessments(baker.make(QuestSubmission, quest=baker.make(Quest), user=self.student), self.teacher)
            self.assertEqual(queued.call_count, 2)

        self.client.force_login(self.teacher)
        with patch('competencies.views.queue_conditions_update') as queued:
            self.client.post(reverse('competencies:override', args=[self.student.pk, self.defining.pk]), {'level': EXT, 'note': ''})
            queued.assert_called_once_with(self.student.pk)


class ConditionsUpdateElsewhereTest(CompetencyPrerequisiteMixin, ByteDeckTenantTestCase):
    """ Levels changed outside the approval and override forms (in the admin, or by the deck's roll-up
    settings) queue the recalculation too, when a prerequisite asks for a competency level. """

    def setUp(self):
        """ Adds a second student, and a prerequisite on the competency. """
        super().setUp()
        self.other = User.objects.create_user('prereq_other_student')
        self.require(PRF)

    def queued_students(self, queued):
        """ The students a patched apply_async was queued for, in order. """
        return [call.kwargs['args'][0] for call in queued.call_args_list]

    def test_queue_conditions_update__several_students_at_once(self):
        """ Every student given is queued; none given queues nothing """
        with patch.object(update_quest_conditions_for_user, 'apply_async') as queued:
            queue_conditions_update()
            queued.assert_not_called()
            queue_conditions_update(self.student.pk, self.other.pk)

        self.assertEqual(self.queued_students(queued), [self.student.pk, self.other.pk])

    def test_queue_conditions_update_for_everyone__only_with_a_competency_prerequisite(self):
        """ The recalculation for every student is queued while a prerequisite asks for a competency, and
        not once none does """
        with patch.object(update_quest_conditions_all_users, 'apply_async') as queued:
            queue_conditions_update_for_everyone()
            queued.assert_called_once_with(args=[1], queue='default', countdown=settings.CONDITIONS_UPDATE_COUNTDOWN)

            Prereq.objects.all().delete()
            queue_conditions_update_for_everyone()
            self.assertEqual(queued.call_count, 1)

    def test_admin__adding_changing_and_deleting_records_queue_the_update(self):
        """ In the admin, adding or changing an override or an assessment queues its student (both students
        when it moves to another), and deleting one, or several at once, queues each student once """
        self.client.force_login(User.objects.create_user('prereq_admin', is_staff=True, is_superuser=True))
        override = CompetencyOverride.objects.create(user=self.student, competency=self.defining, level=PRF, set_by=self.teacher)
        assessments = [self.assess(DEV), self.assess(EMG), CompetencyAssessment.objects.create(
            user=self.other, competency=self.defining, level=EXT, assessed_by=self.teacher,
        )]
        change_url = reverse('admin:competencies_competencyoverride_change', args=[override.pk])

        with patch.object(update_quest_conditions_for_user, 'apply_async') as queued:
            data = {**model_to_dict(override), 'set_by': self.teacher.pk, 'level': EXT}
            self.assertEqual(self.client.post(change_url, data).status_code, 302)
            self.assertEqual(self.queued_students(queued), [self.student.pk])

            queued.reset_mock()
            self.client.post(change_url, {**data, 'user': self.other.pk})
            self.assertEqual(sorted(self.queued_students(queued)), sorted([self.student.pk, self.other.pk]))

            queued.reset_mock()
            response = self.client.post(reverse('admin:competencies_competencyoverride_delete', args=[override.pk]), {'post': 'yes'})
            self.assertEqual(response.status_code, 302)
            self.assertFalse(CompetencyOverride.objects.exists())
            self.assertEqual(self.queued_students(queued), [self.other.pk])

            queued.reset_mock()
            add_data = {'user': self.student.pk, 'competency': self.defining.pk, 'level': PRF, 'assessed_by': self.teacher.pk}
            self.assertEqual(self.client.post(reverse('admin:competencies_competencyassessment_add'), add_data).status_code, 302)
            self.assertEqual(self.queued_students(queued), [self.student.pk])

            queued.reset_mock()
            action = {'action': 'delete_selected', ACTION_CHECKBOX_NAME: [str(a.pk) for a in assessments], 'post': 'yes'}
            self.assertEqual(self.client.post(reverse('admin:competencies_competencyassessment_changelist'), action).status_code, 302)
            self.assertEqual(CompetencyAssessment.objects.count(), 1)
            self.assertEqual(sorted(self.queued_students(queued)), sorted([self.student.pk, self.other.pk]))

    def test_site_config__changing_the_roll_up_queues_the_update_for_everyone(self):
        """ Saving the deck's settings with a new roll-up strategy or count queues the recalculation for
        every student; saving them with other changes doesn't """
        config = SiteConfig.get()
        self.client.force_login(config.deck_owner)
        data = model_to_dict(config, exclude=[
            'banner_image', 'banner_image_dark', 'site_logo', 'default_icon', 'favicon', 'custom_stylesheet', 'custom_javascript',
        ])
        data = {key: value for key, value in data.items() if value is not None}
        url = reverse('config:site_config_update_own')

        with patch.object(update_quest_conditions_all_users, 'apply_async') as queued:
            self.assertEqual(self.client.post(url, {**data, 'site_name': "Renamed Deck"}).status_code, 302)
            queued.assert_not_called()

            self.client.post(url, {**data, 'competency_rollup': RollupStrategy.HIGHEST})
            self.assertEqual(queued.call_count, 1)

            self.client.post(url, {**data, 'competency_rollup': RollupStrategy.HIGHEST, 'competency_rollup_count': 5})
            self.assertEqual(queued.call_count, 2)

        self.assertEqual(SiteConfig.get().competency_rollup_count, 5)


class CompetencyPrerequisiteMapTest(CompetencyPrerequisiteMixin, ByteDeckTenantTestCase):
    """ A map with a quest that also needs a competency level. """

    def test_map__draws_the_quest_and_no_competency_node(self):
        """ A quest that needs an earlier quest and a competency level is drawn after the earlier quest,
        as with a course or grade prerequisite, and the competency gets no node of its own """
        earlier = baker.make(Quest, name="Basics", xp=5)
        Prereq.objects.create(parent_object=self.quest, prereq_object=earlier)
        self.require(PRF)

        scape = CytoScape.generate_map(earlier, "Design Map")

        nodes = CytoElement.objects.filter(scape=scape, group=CytoElement.NODES)
        self.assertTrue(nodes.filter(selector_id=CytoElement.generate_selector_id(self.quest)).exists())
        self.assertFalse(nodes.filter(selector_id=CytoElement.generate_selector_id(self.defining)).exists())
        self.assertEqual(SiteConfig.get().get_competency_scale_labels()[PRF], "Got It")
