from unittest import mock

from django.core.exceptions import ValidationError
from django.utils import timezone

from crispy_forms.utils import render_crispy_form
from model_bakery import baker

from competencies.forms import COMPETENCIES_FIELD, competency_level_field_name, quest_competency_initial
from competencies.models import Competency, ProficiencyLevel, QuestCompetency
from courses.models import Course
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.forms import QuestForm, TAQuestForm
from quest_manager.models import Quest
from siteconfig.models import SiteConfig


def enable_competencies():
    """ Turn the competencies feature flag on for the test deck. """
    config = SiteConfig.get()
    config.enable_competencies = True
    config.full_clean()
    config.save()


class QuestCompetenciesFormTest(ByteDeckTenantTestCase):
    """ Tests for the competency fields QuestCompetenciesFormMixin adds to the quest form. """

    @classmethod
    def setUpTestData(cls):
        """ Valid quest form data, two active competencies and a deactivated one. """
        cls.minimal_valid_data = {
            "name": "Test Quest",
            "xp": 0,
            "max_repeats": 0,
            "max_xp": -1,
            "hours_between_repeats": 0,
            "sort_order": 0,
            "date_available": str(timezone.now().date()),
            "time_available": "0:00:00",
            "tags": "",
        }
        cls.thinking = baker.make(Competency, name="Critical Thinking", category="Thinking")
        cls.communicating = baker.make(Competency, name="Communicating", category="Communication")
        cls.retired = baker.make(Competency, name="Retired Competency", active=False)

    def data(self, competencies=(), **levels):
        """ Quest form data selecting the given competencies, with optional levels.

        Args:
            competencies: the competencies to select.
            **levels: level values keyed by competency attribute name on this test class,
                e.g. thinking=4.

        Returns:
            dict: POST data for QuestForm.
        """
        data = {**self.minimal_valid_data, COMPETENCIES_FIELD: [c.pk for c in competencies]}
        for attr, level in levels.items():
            data[competency_level_field_name(getattr(self, attr).pk)] = level
        return data

    def test_add_competency_fields__absent_when_disabled(self):
        """ With the flag off (the default) the form has no competency fields and renders none """
        form = QuestForm()

        self.assertNotIn(COMPETENCIES_FIELD, form.fields)
        self.assertFalse([name for name in form.fields if name.startswith('competency_level_')])
        self.assertNotIn('quest-competency-levels', render_crispy_form(form))

    def test_add_competency_fields__offers_active_competencies(self):
        """ With the flag on, the active competencies are offered, each with a level picker
        defaulting to Proficient, and the deactivated one is not """
        enable_competencies()
        form = QuestForm()

        self.assertEqual(set(form.fields[COMPETENCIES_FIELD].queryset), {self.thinking, self.communicating})
        self.assertEqual(form.fields[competency_level_field_name(self.thinking.pk)].initial, ProficiencyLevel.PROFICIENT)
        self.assertNotIn(competency_level_field_name(self.retired.pk), form.fields)

    def test_add_competency_fields__options_name_the_course_and_category(self):
        """ The chips field's options read "Course: Category: Name", so like-worded competencies
        from different courses can be told apart; the level table names the course and category too """
        enable_competencies()
        self.thinking.course = baker.make(Course, title='Core')
        self.thinking.full_clean()
        self.thinking.save()

        form = QuestForm(data=self.data([self.thinking]))
        field = form.fields[COMPETENCIES_FIELD]
        rendered = render_crispy_form(form)

        self.assertEqual(field.label_from_instance(self.thinking), 'Core: Thinking: Critical Thinking')
        self.assertIn('>Core: Thinking: Critical Thinking</option>', rendered)
        self.assertIn('<small class="text-muted">Core: Thinking</small>', rendered)

    def test_add_competency_fields__level_choices_use_the_decks_labels(self):
        """ The level pickers show this deck's custom proficiency scale labels """
        enable_competencies()
        config = SiteConfig.get()
        config.competency_label_level_4 = "Exceeding"
        config.full_clean()
        config.save()

        choices = dict(QuestForm().fields[competency_level_field_name(self.thinking.pk)].choices)
        self.assertEqual(choices[ProficiencyLevel.EXTENDING], "Exceeding")

    def test_add_competency_fields__keeps_a_linked_deactivated_competency(self):
        """ A deactivated competency already linked to the quest stays offered and selected,
        with its level, so saving the form doesn't silently drop the link """
        enable_competencies()
        quest = baker.make(Quest)
        QuestCompetency.objects.create(quest=quest, competency=self.retired, default_level=ProficiencyLevel.DEVELOPING)

        form = QuestForm(instance=quest)

        self.assertIn(self.retired, form.fields[COMPETENCIES_FIELD].queryset)
        self.assertEqual(form.fields[COMPETENCIES_FIELD].initial, [self.retired.pk])
        self.assertEqual(form.fields[competency_level_field_name(self.retired.pk)].initial, ProficiencyLevel.DEVELOPING)

    def test_add_competency_fields__renders_in_the_crispy_layout(self):
        """ The chips field and the level table render through the form's crispy layout, for
        the TA form too, with only the selected competency's level row shown """
        enable_competencies()
        for form_class in (QuestForm, TAQuestForm):
            with self.subTest(form=form_class.__name__):
                rendered = render_crispy_form(form_class(data=self.data([self.thinking])))

                self.assertIn(f'name="{COMPETENCIES_FIELD}"', rendered)
                self.assertIn('id="quest-competency-levels"', rendered)
                self.assertIn(f'name="{competency_level_field_name(self.thinking.pk)}"', rendered)
                self.assertIn(f'<tr data-competency-id="{self.thinking.pk}">', rendered)
                self.assertIn(f'<tr data-competency-id="{self.communicating.pk}" class="hidden">', rendered)

    def test_competency_levels__marks_the_selected_rows(self):
        """ competency_levels() marks the selected competencies' rows, and reports when none are """
        enable_competencies()

        levels = QuestForm(data=self.data([self.thinking])).competency_levels()
        self.assertEqual({competency: selected for competency, _field, selected in levels['rows']},
                         {self.thinking: True, self.communicating: False})
        self.assertTrue(levels['any_selected'])

        self.assertFalse(QuestForm().competency_levels()['any_selected'])

    def test_save__creates_links_with_their_levels(self):
        """ Selected competencies are linked with their chosen level, or Proficient when none is posted """
        enable_competencies()
        form = QuestForm(data=self.data([self.thinking, self.communicating], thinking=ProficiencyLevel.EXTENDING))
        self.assertTrue(form.is_valid(), form.errors)

        quest = form.save()

        self.assertEqual(
            dict(QuestCompetency.objects.filter(quest=quest).values_list('competency', 'default_level')),
            {self.thinking.pk: ProficiencyLevel.EXTENDING, self.communicating.pk: ProficiencyLevel.PROFICIENT},
        )

    def test_save__updates_levels_and_removes_deselected_links(self):
        """ Saving changes a kept link's level and removes the links of deselected competencies """
        enable_competencies()
        quest = baker.make(Quest)
        QuestCompetency.objects.create(quest=quest, competency=self.thinking, default_level=ProficiencyLevel.DEVELOPING)
        QuestCompetency.objects.create(quest=quest, competency=self.communicating)

        form = QuestForm(data=self.data([self.thinking], thinking=ProficiencyLevel.EXTENDING), instance=quest)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.assertEqual(
            dict(QuestCompetency.objects.filter(quest=quest).values_list('competency', 'default_level')),
            {self.thinking.pk: ProficiencyLevel.EXTENDING},
        )

    def test_save__unchanged_link_is_not_rewritten(self):
        """ A kept link whose level didn't change is not saved again """
        enable_competencies()
        quest = baker.make(Quest)
        link = QuestCompetency.objects.create(quest=quest, competency=self.thinking, default_level=ProficiencyLevel.DEVELOPING)

        form = QuestForm(data=self.data([self.thinking], thinking=ProficiencyLevel.DEVELOPING), instance=quest)
        self.assertTrue(form.is_valid(), form.errors)
        with mock.patch.object(QuestCompetency, 'save') as save:
            form.save()

        save.assert_not_called()
        self.assertEqual(list(QuestCompetency.objects.filter(quest=quest).values_list('pk', 'default_level')),
                         [(link.pk, ProficiencyLevel.DEVELOPING)])

    def test_save__link_failure_rolls_back_the_quest(self):
        """ The quest and its links save together: if a link fails to save, the quest isn't saved either """
        enable_competencies()
        form = QuestForm(data=self.data([self.thinking]))
        self.assertTrue(form.is_valid(), form.errors)

        with mock.patch.object(QuestCompetency, 'full_clean', side_effect=ValidationError("bad link")):
            with self.assertRaises(ValidationError):
                form.save()

        self.assertFalse(Quest.objects.filter(name="Test Quest").exists())

    def test_save__commit_false_leaves_the_links_to_the_caller(self):
        """ With commit=False nothing is saved; the caller saves the quest, then save_competencies() """
        enable_competencies()
        form = QuestForm(data=self.data([self.thinking]))
        self.assertTrue(form.is_valid(), form.errors)

        quest = form.save(commit=False)
        quest.save()
        self.assertFalse(QuestCompetency.objects.filter(quest=quest).exists())

        form.save_competencies(quest)
        self.assertTrue(QuestCompetency.objects.filter(quest=quest, competency=self.thinking).exists())

    def test_save__ignores_posted_competencies_when_disabled(self):
        """ With the flag off, competency data in a POST is ignored: no links are made """
        form = QuestForm(data=self.data([self.thinking], thinking=ProficiencyLevel.EXTENDING))
        self.assertTrue(form.is_valid(), form.errors)

        quest = form.save()

        self.assertFalse(QuestCompetency.objects.filter(quest=quest).exists())

    def test_clean__rejects_an_invalid_level(self):
        """ A level outside the 4-point scale is a form error on that competency's level field """
        enable_competencies()
        form = QuestForm(data=self.data([self.thinking], thinking=9))

        self.assertFalse(form.is_valid())
        self.assertIn(competency_level_field_name(self.thinking.pk), form.errors)

    def test_quest_competency_initial__carries_active_links_and_levels(self):
        """ The copy helper selects the quest's active competencies with their levels, and
        leaves out a deactivated one """
        quest = baker.make(Quest)
        QuestCompetency.objects.create(quest=quest, competency=self.thinking, default_level=ProficiencyLevel.EXTENDING)
        QuestCompetency.objects.create(quest=quest, competency=self.retired)

        self.assertEqual(quest_competency_initial(quest), {
            COMPETENCIES_FIELD: [self.thinking.pk],
            competency_level_field_name(self.thinking.pk): ProficiencyLevel.EXTENDING,
        })
