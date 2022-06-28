# from mock import patch

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import models

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker

from prerequisites.models import IsAPrereqMixin, Prereq, PrereqAllConditionsMet

User = get_user_model()


class HasPrereqsMixinTest(TenantTestCase):
    def setUp(self):
        self.quest_parent = baker.make('quest_manager.Quest', name="parent")
        self.quest_prereq = baker.make('quest_manager.Quest', name="prereq")
        self.quest_or_prereq = baker.make('quest_manager.Quest', name="or_prereq")

        self.prereq_with_or = Prereq.objects.create(
            parent_object=self.quest_parent,
            prereq_object=self.quest_prereq,
            or_prereq_object=self.quest_or_prereq
        )

        self.quest_prereq2 = baker.make('quest_manager.Quest', name="prereq2")

        self.prereq_without_or = Prereq.objects.create(
            parent_object=self.quest_parent,
            prereq_object=self.quest_prereq2,
        )

    def test_prereqs(self):
        """Returns the 2 prereqs created in setup"""
        prereqs = self.quest_parent.prereqs()
        self.assertEqual(len(prereqs), 2)

    def test_add_simple_prereqs(self):
        """Adds 3 new prereqs using this method"""
        prereq_objects = [
            baker.make('quest_manager.Quest'),
            baker.make('quest_manager.Quest'),
            baker.make('quest_manager.Quest'),
        ]
        self.quest_parent.add_simple_prereqs(prereq_objects)
        self.assertEqual(self.quest_parent.prereqs().count(), 5)

    def test_add_simple_prereqs_type_error(self):
        """Objects that do not implement the `IsAPrereqMixin` should throw a type error"""
        with self.assertRaises(TypeError):
            self.quest_parent.add_simple_prereqs([object()])

    def test_clear_all_prereqs(self):
        self.quest_parent.clear_all_prereqs()
        self.assertEqual(self.quest_parent.prereqs().count(), 0)

    def test_has_or_prereq(self):
        """ When there is an OR prereq, both should return True"""
        self.assertTrue(self.quest_parent.has_or_prereq(self.quest_or_prereq))
        self.assertTrue(self.quest_parent.has_or_prereq(self.quest_prereq))
        self.assertFalse(self.quest_parent.has_or_prereq(self.quest_prereq2))

    def test_has_or_prereq_exclude_NOT(self):
        """ When there is an OR prereq, both should return True, unless it's a NOT"""
        self.prereq_with_or.prereq_invert = True
        self.prereq_with_or.save()

        self.assertTrue(self.quest_parent.has_or_prereq(self.quest_or_prereq))
        self.assertFalse(self.quest_parent.has_or_prereq(self.quest_prereq))
        self.assertFalse(self.quest_parent.has_or_prereq(self.quest_prereq2))

        self.assertTrue(self.quest_parent.has_or_prereq(self.quest_or_prereq, exclude_NOT=False))
        self.assertTrue(self.quest_parent.has_or_prereq(self.quest_prereq, exclude_NOT=False))
        self.assertFalse(self.quest_parent.has_or_prereq(self.quest_prereq2, exclude_NOT=False))

    def test_has_or_prereq_type_error(self):
        with self.assertRaises(TypeError):
            self.quest_parent.has_or_prereq(object())

    def test_has_or_prereq_no_object(self):
        """If no object is provided, should check if there are any OR prereqs at all"""
        self.assertTrue(self.quest_parent.has_or_prereq())

        Prereq.objects.create(
            parent_object=self.quest_prereq2,
            prereq_object=baker.make('quest_manager.Quest'),
        )
        self.assertFalse(self.quest_prereq2.has_or_prereq())

    def test_has_or_prereq_no_object_exclude_NOT(self):
        self.prereq_with_or.prereq_invert = True
        self.prereq_with_or.save()
        self.assertFalse(self.quest_parent.has_or_prereq())
        self.assertTrue(self.quest_parent.has_or_prereq(exclude_NOT=False))

    def test_has_inverted_prereq(self):
        self.assertFalse(self.quest_parent.has_inverted_prereq())

        self.prereq_with_or.prereq_invert = True
        self.prereq_with_or.save()
        self.assertTrue(self.quest_parent.has_inverted_prereq())


class IsAPrereqMixinTest(TenantTestCase):
    def setUp(self):
        self.quest_parent = baker.make('quest_manager.Quest', name="parent")
        self.quest_prereq = baker.make('quest_manager.Quest', name="prereq")
        self.quest_or_prereq = baker.make('quest_manager.Quest', name="or_prereq")

        self.prereq_with_or = Prereq.objects.create(
            parent_object=self.quest_parent,
            prereq_object=self.quest_prereq,
            or_prereq_object=self.quest_or_prereq
        )

        self.quest_prereq2 = baker.make('quest_manager.Quest', name="prereq2")

        self.prereq_without_or = Prereq.objects.create(
            parent_object=self.quest_parent,
            prereq_object=self.quest_prereq2,
        )

    def test_is_used_prereq(self):
        self.assertTrue(self.quest_prereq.is_used_prereq())
        self.assertFalse(baker.make('quest_manager.Quest').is_used_prereq())

    def test_get_reliant_qs(self):
        reliant = self.quest_prereq.get_reliant_qs()
        
        self.assertListEqual(list(reliant), list(Prereq.objects.all_reliant_on(self.quest_prereq)))

    def test_get_reliant_objects(self):
        reliant_objects = self.quest_prereq.get_reliant_objects()
        self.assertListEqual(list(reliant_objects), [self.quest_parent])
        # try adding another, this time as an OR
        Prereq.objects.create(
            parent_object=self.quest_prereq2,
            prereq_object=baker.make('quest_manager.Quest'),
            or_prereq_object=self.quest_prereq,
        )

        reliant_objects = self.quest_prereq.get_reliant_objects()
        self.assertListEqual(list(reliant_objects), [self.quest_parent, self.quest_prereq2])

    def test_get_reliant_objects__exclude_NOT(self):
        reliant_objects = self.quest_prereq.get_reliant_objects(exclude_NOT=True)
        self.assertListEqual(list(reliant_objects), [self.quest_parent])

        # or requirement isn't the object we're checking, so inverting it shouldn't make a difference.
        self.prereq_with_or.or_prereq_invert = True
        self.prereq_with_or.save()
        reliant_objects = self.quest_prereq.get_reliant_objects(exclude_NOT=True)
        self.assertEqual(len(reliant_objects), 1)

        self.prereq_with_or.prereq_invert = True
        self.prereq_with_or.save()
        reliant_objects = self.quest_prereq.get_reliant_objects(exclude_NOT=True)
        self.assertEqual(len(reliant_objects), 0)

        reliant_objects = self.quest_prereq.get_reliant_objects(exclude_NOT=False)
        self.assertEqual(len(reliant_objects), 1)

    def test_get_reliant_objects__sort(self):
        """ Test that get_reliant_objects(sort=True) returns a list where the objects are sorted alphabetically by str() """

        # Setup creates self.quest_prereq relying on self.quest_parent.  
        # Add some more reliant quests to be sorted.
        quest_A = baker.make('quest_manager.Quest', name="A")
        quest_z = baker.make('quest_manager.Quest', name="z")
        quest_Z = baker.make('quest_manager.Quest', name="Z")
        Prereq.objects.create(parent_object=quest_Z, prereq_object=self.quest_prereq)
        Prereq.objects.create(parent_object=quest_z, prereq_object=self.quest_prereq)
        Prereq.objects.create(parent_object=quest_A, prereq_object=self.quest_prereq)

        # throw in a Badge
        badge_B = baker.make('badges.Badge', name="B")
        badge_1 = baker.make('badges.Badge', name="1")
        Prereq.objects.create(parent_object=badge_B, prereq_object=self.quest_prereq)
        Prereq.objects.create(parent_object=badge_1, prereq_object=self.quest_prereq)

        reliant_objects = self.quest_prereq.get_reliant_objects(exclude_NOT=True, sort=True)
        # Note lowercase comes after uppercase in the defaults alphanumeric sort
        self.assertListEqual(reliant_objects, [badge_1, quest_A, badge_B, quest_Z, self.quest_parent, quest_z])

    def test_condition_met_as_prerequisite__is_implemented(self):
        """ All models that inherit from this mixin should implement the condition_met_as_prerequisite() method """
        for ct in IsAPrereqMixin.all_registered_content_types():
            # If the method is not implemented, then NotImplementedError is thrown
            instance = baker.make(ct.model_class())
            instance.condition_met_as_prerequisite(user=baker.make(User), num_required=1)

    def test_dal_autocomplete_search_fields__is_implemented(self):
        """ All models implementing this Mixin, also implement this method if the default doesn't suffice """
        prereq_models = IsAPrereqMixin.all_registered_model_classes()
        for model in prereq_models:
            field_name = model.dal_autocomplete_search_fields()
            model._meta.get_field(field_name)

    def test_static_content_type_is_registered(self):
        """A content_type representing a model that implements the IsAPrereqMixin returns True
        """
        ct = ContentType.objects.get(app_label='quest_manager', model='quest')
        self.assertTrue(IsAPrereqMixin.content_type_is_registered(ct))

        ct = ContentType.objects.get(app_label='auth', model='user')
        self.assertFalse(IsAPrereqMixin.content_type_is_registered(ct))

    def test_static_all_registered_content_types(self):
        """There are 6 models that implement the IsAPrereqMixin
        """
        cts = IsAPrereqMixin.all_registered_content_types()
        self.assertEqual(cts.count(), 7)

    def test_static_model_is_registered(self):
        """Any model class that implements IsAPrereqMixin returns True"""
        class TestClassRegistered(IsAPrereqMixin, models.Model):
            pass

        class TestClassNotRegsistered(models.Model):
            pass

        self.assertTrue(IsAPrereqMixin.model_is_registered(TestClassRegistered))
        self.assertFalse(IsAPrereqMixin.model_is_registered(TestClassNotRegsistered))


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

    def test_cls_add_simple_prereq_bad_parent(self):
        """A parent_object that does not implement the HasPrereqsMixin should raise an exception
        """
        with self.assertRaises(TypeError):
            quest3 = baker.make('quest_manager.Quest')
            some_object = object()
            Prereq.add_simple_prereq(some_object, quest3)

    def test_cls_add_simple_prereq_bad_prereq(self):
        """A prereq_object that does not implement the IsAPrereqMixin should raise an exception
        """
        with self.assertRaises(TypeError):
            quest3 = baker.make('quest_manager.Quest')
            some_object = object()
            Prereq.add_simple_prereq(quest3, some_object)


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
