from django.utils import timezone

from django_tenants.test.cases import TenantTestCase

from quest_manager.forms import QuestForm


class QuestFormTest(TenantTestCase):

    def setUp(self):
        self.minimal_valid_data = {
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

    def test_minimal_valid_data(self):
        """The minimal_valid_data provided in the setup method should be valid!"""
        form = QuestForm(data=self.minimal_valid_data)
        self.assertTrue(form.is_valid())

    def test_hideable_blocking_both_true(self):
        """If a quest is Blocking then it should not validate if it is also Hideable"""
        form_data = self.minimal_valid_data

        form_data["hideable"] = True
        form_data["blocking"] = True

        form = QuestForm(data=form_data)
        self.assertFalse(form.is_valid())
        self.assertIn("Blocking quests cannot be Hideable.", form.errors['__all__'][0])
