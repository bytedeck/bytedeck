# from mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType

from model_bakery import baker
from tenant_schemas.test.cases import TenantTestCase

from prerequisites.models import PrereqAllConditionsMet, Prereq, IsAPrereqMixin

User = get_user_model()


class PrereqModelTest(TenantTestCase):
    def setUp(self):
        self.student = baker.make(User, username='student', is_staff=False)
        self.quest_parent = baker.make('quest_manager.Quest')
        self.quest_prereq = baker.make('quest_manager.Quest')
        self.prereq = Prereq(
            parent_object=self.quest_parent,
            prereq_object=self.quest_prereq
        )
    
    def test_object_creation(self):
        self.assertIsInstance(self.prereq, Prereq)
        self.assertIsInstance(self.prereq, IsAPrereqMixin)

    def test_parent(self):
        "returns the parent of the prereq"
        self.assertEqual(self.prereq.parent(), self.quest_parent)

    def test_get_prereq(self):
        "returns the main prereq requirement"
        self.assertEqual(self.prereq.get_prereq(), self.quest_prereq)

    def test_get_or_prereq(self):
        "returns the alternate prereq requirement"
        self.assertEqual(self.prereq.get_or_prereq(), None)

    # Todo: need some massive mocking for this one
    # @patch('prereq_object.condition_met_as_prerequisite', return_value=True)
    # def test_conditions_met(self, condition_met_as_prerequisite):
    #     print("Call count: ", condition_met_as_prerequisite.call_count)
    #     self.assertTrue(self.prereq.condition_met(self.student))

    def test_cls_add_simple_prereq(self):
        quest3 = baker.make('quest_manager.Quest')
        Prereq.add_simple_prereq(self.quest_parent, quest3)
        self.assertIn(self.quest_parent, quest3.get_reliant_objects())

    # def test_cls_add_simple_prereq_bad_parent(self):
    #     """A parent_object that does not implement the HasPrereqsMixin should raise an exception
    #     """
    #     with self.assertRaises(TypeError):
    #         quest3 = baker.make('quest_manager.Quest')
    #         some_object = object()
    #         Prereq.add_simple_prereq(some_object, quest3)

    def test_cls_model_is_registered(self):
        """A model that implements the IsAPrereqMixin returns True
        """
        ct = ContentType.objects.get(app_label='quest_manager', model='quest')
        self.assertTrue(Prereq.model_is_registered(ct))

        ct = ContentType.objects.get(app_label='auth', model='user')
        self.assertFalse(Prereq.model_is_registered(ct))  

    def test_all_registered_content_types(self):
        """There are 6 models that implement the IsAPrereqMixin
        """
        cts = Prereq.all_registered_content_types()
        self.assertEqual(cts.count(), 6)


class PrereqAllConditionsMetModelTest(TenantTestCase):

    def setUp(self):
        self.student = baker.make(User, username='student', is_staff=False)
        self.prereq_cache = baker.make(
            PrereqAllConditionsMet,
            user=self.student,
            model_name='fake_model_name'
        )

    def test_object_creation(self):
        self.assertIsInstance(self.prereq_cache, PrereqAllConditionsMet)
        self.assertEqual(self.prereq_cache.user, self.student)
        self.assertEqual(self.prereq_cache.ids, '[]')

    def test_get_ids_when_empty(self):
        self.assertEqual([], self.prereq_cache.get_ids())

    def test_get_ids(self):
        ids = [1, 2, 3, 4, 5]
        self.prereq_cache.ids = str(ids)
        self.assertEqual(ids, self.prereq_cache.get_ids())

    def test_add_id(self):
        self.assertEqual(len(self.prereq_cache.get_ids()), 0)

        self.prereq_cache.add_id(100)
        self.assertEqual(len(self.prereq_cache.get_ids()), 1)
        self.assertEqual(self.prereq_cache.get_ids(), [100])

        self.prereq_cache.add_id(101)
        self.assertEqual(len(self.prereq_cache.get_ids()), 2)
        self.assertEqual(self.prereq_cache.get_ids(), [100, 101])

    def test_remove_id(self):
        self.prereq_cache.ids = str([1, 2, 3, 4, 5])
        self.assertIn(1, self.prereq_cache.get_ids())

        self.prereq_cache.remove_id(1)
        self.assertNotIn(1, self.prereq_cache.get_ids())

    def test_remove_id_that_doesnt_exist(self):
        ids = [1, 2, 3, 4, 5]
        self.prereq_cache.ids = str(ids)
        self.assertNotIn(6, self.prereq_cache.get_ids())

        self.prereq_cache.remove_id(6)
        self.assertNotIn(6, self.prereq_cache.get_ids())
        self.assertEqual(len(self.prereq_cache.get_ids()), len(ids))
