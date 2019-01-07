import djconfig
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from model_mommy import mommy
from model_mommy.recipe import Recipe

from profile_manager.models import Profile, smart_list
from quest_manager.models import Quest


class ProfileTestModel(TestCase):

    def setUp(self):
        djconfig.reload_maybe()  # https://github.com/nitely/django-djconfig/issues/31#issuecomment-451587942

        User = get_user_model()
        self.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        self.user = mommy.make(User)
        # Profiles are created automatically with each user, so we only need to access profiles via users
        self.profile = self.user.profile

    def test_profile_creation(self):
        self.assertIsInstance(self.user.profile, Profile)
        self.assertEqual(str(self.user.profile), self.user.username)

    def test_profile_alias_clipped(self):
        max_len = 16
        self.assertEqual(self.profile.alias_clipped(), "-")

        self.profile.alias = "Short Alias"
        self.assertEqual(self.profile.alias_clipped(), self.profile.alias)

        self.profile.alias = "Super duper duper long alias that's super duper long"
        self.assertEqual(len(self.profile.alias_clipped()), max_len)

    def test_profile_num_hidden_quests(self):
        self.assertEqual(self.profile.num_hidden_quests(), 0)
        # TODO add some hidden quests and test

    def test_profile_get_hidden_quests_as_list(self):
        self.assertEqual(self.profile.get_hidden_quests_as_list(), [])
        # TODO add some hidden quests and test

    def test_profile_hidden_quests(self):
        num_to_hide = 3
        quests_to_hide = mommy.make(Quest, _quantity=num_to_hide)
        hidden_quest_list = [str(q.pk) for q in quests_to_hide]

        self.profile.save_hidden_quests_from_list(hidden_quest_list)

        self.assertEqual(self.profile.num_hidden_quests(), num_to_hide)

        quest_hidden = quests_to_hide[0]
        self.assertTrue(self.profile.is_quest_hidden(quest_hidden))

        quest_not_hidden = mommy.make(Quest)
        self.assertFalse(self.profile.is_quest_hidden(quest_not_hidden))
        self.assertEqual(self.profile.get_hidden_quests_as_list(), hidden_quest_list)

        self.profile.hide_quest(quest_not_hidden.id)
        self.assertTrue(self.profile.is_quest_hidden(quest_not_hidden))

        self.profile.unhide_quest(quest_hidden.id)
        self.assertFalse(self.profile.is_quest_hidden(quest_hidden))


class SmartListTests(SimpleTestCase):

    def test_smart_list_empty(self):
        self.assertEqual(smart_list(''), [])
        self.assertEqual(smart_list([]), [])
        self.assertEqual(smart_list('[]'), [])
        self.assertEqual(smart_list(None), [])

    def test_smart_list_csv(self):
        self.assertEqual(smart_list('1,2,3'), ['1', '2', '3'])

    def test_smart_list_csv_delimeter(self):
        self.assertEqual(smart_list('1;2;3', delimiter=';'), ['1', '2', '3'])

    def test_smart_list_csv_to_int(self):
            self.assertEqual(smart_list('1,2,3', func=lambda x: int(x)), [1, 2, 3])

    def test_smart_list_tuple(self):
        self.assertEqual(smart_list((1, 2, 3)),  [1, 2, 3])

    def test_smart_list_list(self):
        self.assertEqual(smart_list([1, 2, 3]),  [1, 2, 3])

    def test_smart_list_int(self):
        self.assertEqual(smart_list(1),  [1])
