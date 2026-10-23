from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from model_bakery import baker

from competencies.forms import COMPETENCIES_FIELD, competency_level_field_name
from competencies.models import Competency, ProficiencyLevel, QuestCompetency
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest
from siteconfig.models import SiteConfig

User = get_user_model()


class QuestCompetencyViewsTest(ByteDeckTenantTestCase):
    """ Competencies on the quest create, update, copy and detail views. """

    @classmethod
    def setUpTestData(cls):
        """ A teacher, a student, two competencies, and valid quest form POST data. """
        cls.teacher = baker.make(User, is_staff=True)
        cls.student = baker.make(User)
        cls.thinking = baker.make(Competency, name="Critical Thinking", category="Thinking")
        cls.communicating = baker.make(Competency, name="Communicating", category="Communication")
        cls.post_data = {
            "name": "Competency Quest",
            "xp": 0,
            "max_repeats": 0,
            "max_xp": -1,
            "hours_between_repeats": 0,
            "sort_order": 0,
            "date_available": str(timezone.now().date()),
            "time_available": "0:00:00",
            "tags": "",
        }

    def setUp(self):
        """ Turn the competencies feature flag on and sign the teacher in. """
        self.set_flag(True)
        self.client.force_login(self.teacher)

    def set_flag(self, enabled, **labels):
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

    def links(self, quest):
        """ The quest's competency links as {competency pk: default level}. """
        return dict(QuestCompetency.objects.filter(quest=quest).values_list('competency', 'default_level'))

    def test_quest_create__attaches_competencies_with_levels(self):
        """ Creating a quest with competencies selected links them at the chosen levels """
        self.client.post(reverse('quests:quest_create'), data={
            **self.post_data,
            COMPETENCIES_FIELD: [self.thinking.pk, self.communicating.pk],
            competency_level_field_name(self.thinking.pk): ProficiencyLevel.EXTENDING,
        })

        quest = Quest.objects.get(name="Competency Quest")
        self.assertEqual(self.links(quest), {
            self.thinking.pk: ProficiencyLevel.EXTENDING,
            self.communicating.pk: ProficiencyLevel.PROFICIENT,
        })

    def test_quest_update__changes_levels_and_detaches(self):
        """ Updating a quest changes a link's level and detaches a deselected competency """
        quest = baker.make(Quest, name="Competency Quest")
        QuestCompetency.objects.create(quest=quest, competency=self.thinking)
        QuestCompetency.objects.create(quest=quest, competency=self.communicating)

        self.client.post(reverse('quests:quest_update', args=[quest.pk]), data={
            **self.post_data,
            COMPETENCIES_FIELD: [self.thinking.pk],
            competency_level_field_name(self.thinking.pk): ProficiencyLevel.EMERGING,
        })

        self.assertEqual(self.links(quest), {self.thinking.pk: ProficiencyLevel.EMERGING})

    def test_quest_update__form_shows_the_quests_competencies(self):
        """ The update form shows the chips field with the linked competency selected, and its level row """
        quest = baker.make(Quest)
        QuestCompetency.objects.create(quest=quest, competency=self.thinking, default_level=ProficiencyLevel.DEVELOPING)

        response = self.client.get(reverse('quests:quest_update', args=[quest.pk]))

        self.assertContains(response, 'id="quest-competency-levels"')
        self.assertContains(response, f'<tr data-competency-id="{self.thinking.pk}">')
        self.assertContains(response, 'competencies/js/quest-competency-levels.js')

    def test_quest_create__form_has_no_competencies_when_disabled(self):
        """ With the flag off the create form has no competency fields, and posting them links nothing """
        self.set_flag(False)

        response = self.client.get(reverse('quests:quest_create'))
        self.assertNotContains(response, f'name="{COMPETENCIES_FIELD}"')
        self.assertNotContains(response, 'quest-competency-levels')

        self.client.post(reverse('quests:quest_create'), data={**self.post_data, COMPETENCIES_FIELD: [self.thinking.pk]})
        self.assertTrue(Quest.objects.filter(name="Competency Quest").exists())
        self.assertFalse(QuestCompetency.objects.exists())

    def test_quest_copy__carries_the_competencies_over(self):
        """ Copying a quest starts the copy with the source's competencies and levels, and saving it links them """
        source = baker.make(Quest, name="Source Quest")
        QuestCompetency.objects.create(quest=source, competency=self.thinking, default_level=ProficiencyLevel.EXTENDING)

        response = self.client.get(reverse('quests:quest_copy', args=[source.pk]))
        self.assertEqual(response.context['form'][COMPETENCIES_FIELD].value(), [self.thinking.pk])
        self.assertContains(response, f'<tr data-competency-id="{self.thinking.pk}">')

        self.client.post(reverse('quests:quest_copy', args=[source.pk]), data={
            **self.post_data,
            "name": "Source Quest - COPY",
            COMPETENCIES_FIELD: [self.thinking.pk],
            competency_level_field_name(self.thinking.pk): ProficiencyLevel.EXTENDING,
        })

        copy = Quest.objects.get(name="Source Quest - COPY")
        self.assertEqual(self.links(copy), {self.thinking.pk: ProficiencyLevel.EXTENDING})

    def test_quest_detail__staff_see_chips_with_levels(self):
        """ Staff see each competency as a chip with its default level, in the deck's own labels """
        self.set_flag(True, competency_label_level_4="Exceeding")
        quest = baker.make(Quest)
        QuestCompetency.objects.create(quest=quest, competency=self.thinking, default_level=ProficiencyLevel.EXTENDING)

        response = self.client.get(reverse('quests:quest_detail', args=[quest.pk]))

        self.assertContains(response, '<span class="label label-info competency-chip">Critical Thinking: Exceeding</span>', html=True)

    def test_quest_detail__students_see_competency_names(self):
        """ Students see the quest's competency names, without the default levels """
        quest = baker.make(Quest, published=True)
        QuestCompetency.objects.create(quest=quest, competency=self.thinking)
        self.client.force_login(self.student)

        with patch('quest_manager.models.Quest.is_available', return_value=False):
            response = self.client.get(reverse('quests:quest_detail', args=[quest.pk]))

        self.assertContains(response, '<span class="label label-info competency-chip">Critical Thinking</span>', html=True)

    def test_quest_detail__no_chips_when_disabled_or_none_attached(self):
        """ No competencies line when the flag is off, nor on a quest without competencies """
        quest = baker.make(Quest)
        bare_quest = baker.make(Quest)
        QuestCompetency.objects.create(quest=quest, competency=self.thinking)

        self.assertNotContains(self.client.get(reverse('quests:quest_detail', args=[bare_quest.pk])), 'competency-chip')

        self.set_flag(False)
        self.assertNotContains(self.client.get(reverse('quests:quest_detail', args=[quest.pk])), 'competency-chip')
