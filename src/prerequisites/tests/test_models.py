from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.utils import IntegrityError
from django.test.utils import isolate_apps

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from prerequisites.models import IsAPrereqMixin, Prereq, PrereqAllConditionsMet

from psycopg2.errors import UndefinedTable

User = get_user_model()


class HasPrereqsMixinTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Create a parent quest with an OR prereq and a plain prereq."""
        cls.quest_parent = baker.make('quest_manager.Quest', name="parent")
        cls.quest_prereq = baker.make('quest_manager.Quest', name="prereq")
        cls.quest_or_prereq = baker.make('quest_manager.Quest', name="or_prereq")

        cls.prereq_with_or = Prereq.objects.create(
            parent_object=cls.quest_parent,
            prereq_object=cls.quest_prereq,
            or_prereq_object=cls.quest_or_prereq
        )

        cls.quest_prereq2 = baker.make('quest_manager.Quest', name="prereq2")

        cls.prereq_without_or = Prereq.objects.create(
            parent_object=cls.quest_parent,
            prereq_object=cls.quest_prereq2,
        )

    def test_prereqs__returns_all_prereqs(self):
        """Returns the 2 prereqs created in setup"""
        prereqs = self.quest_parent.prereqs()
        self.assertEqual(len(prereqs), 2)

    def test_add_simple_prereqs__adds_multiple(self):
        """Adds 3 new prereqs using this method"""
        prereq_objects = [
            baker.make('quest_manager.Quest'),
            baker.make('quest_manager.Quest'),
            baker.make('quest_manager.Quest'),
        ]
        self.quest_parent.add_simple_prereqs(prereq_objects)
        self.assertEqual(self.quest_parent.prereqs().count(), 5)

    def test_add_simple_prereqs__type_error(self):
        """Objects that do not implement the `IsAPrereqMixin` should throw a type error"""
        with self.assertRaises(TypeError):
            self.quest_parent.add_simple_prereqs([object()])

    def test_clear_all_prereqs__removes_all(self):
        """clear_all_prereqs removes every prereq of the parent."""
        self.quest_parent.clear_all_prereqs()
        self.assertEqual(self.quest_parent.prereqs().count(), 0)

    def test_has_or_prereq__true_for_main_and_or_requirement(self):
        """ When there is an OR prereq, both should return True"""
        self.assertTrue(self.quest_parent.has_or_prereq(self.quest_or_prereq))
        self.assertTrue(self.quest_parent.has_or_prereq(self.quest_prereq))
        self.assertFalse(self.quest_parent.has_or_prereq(self.quest_prereq2))

    def test_has_or_prereq__exclude_NOT(self):
        """ When there is an OR prereq, both should return True, unless it's a NOT"""
        self.prereq_with_or.prereq_invert = True
        self.prereq_with_or.save()

        self.assertTrue(self.quest_parent.has_or_prereq(self.quest_or_prereq))
        self.assertFalse(self.quest_parent.has_or_prereq(self.quest_prereq))
        self.assertFalse(self.quest_parent.has_or_prereq(self.quest_prereq2))

        self.assertTrue(self.quest_parent.has_or_prereq(self.quest_or_prereq, exclude_NOT=False))
        self.assertTrue(self.quest_parent.has_or_prereq(self.quest_prereq, exclude_NOT=False))
        self.assertFalse(self.quest_parent.has_or_prereq(self.quest_prereq2, exclude_NOT=False))

    def test_has_or_prereq__type_error(self):
        """A non-prereq object passed to has_or_prereq raises a TypeError."""
        with self.assertRaises(TypeError):
            self.quest_parent.has_or_prereq(object())

    def test_has_or_prereq__no_object(self):
        """If no object is provided, should check if there are any OR prereqs at all"""
        self.assertTrue(self.quest_parent.has_or_prereq())

        Prereq.objects.create(
            parent_object=self.quest_prereq2,
            prereq_object=baker.make('quest_manager.Quest'),
        )
        self.assertFalse(self.quest_prereq2.has_or_prereq())

    def test_has_or_prereq__no_object_exclude_NOT(self):
        """With no object, an inverted OR prereq is only counted when exclude_NOT is False."""
        self.prereq_with_or.prereq_invert = True
        self.prereq_with_or.save()
        self.assertFalse(self.quest_parent.has_or_prereq())
        self.assertTrue(self.quest_parent.has_or_prereq(exclude_NOT=False))

    def test_has_inverted_prereq__reflects_prereq_invert(self):
        """has_inverted_prereq is True once one of the parent's prereqs is inverted."""
        self.assertFalse(self.quest_parent.has_inverted_prereq())

        self.prereq_with_or.prereq_invert = True
        self.prereq_with_or.save()
        self.assertTrue(self.quest_parent.has_inverted_prereq())


class IsAPrereqMixinTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Create a parent quest with an OR prereq and a plain prereq."""
        cls.quest_parent = baker.make('quest_manager.Quest', name="parent")
        cls.quest_prereq = baker.make('quest_manager.Quest', name="prereq")
        cls.quest_or_prereq = baker.make('quest_manager.Quest', name="or_prereq")

        cls.prereq_with_or = Prereq.objects.create(
            parent_object=cls.quest_parent,
            prereq_object=cls.quest_prereq,
            or_prereq_object=cls.quest_or_prereq
        )

        cls.quest_prereq2 = baker.make('quest_manager.Quest', name="prereq2")

        cls.prereq_without_or = Prereq.objects.create(
            parent_object=cls.quest_parent,
            prereq_object=cls.quest_prereq2,
        )

    def test_is_used_prereq__true_when_used(self):
        """is_used_prereq is True for an object used as a prereq, False otherwise."""
        self.assertTrue(self.quest_prereq.is_used_prereq())
        self.assertFalse(baker.make('quest_manager.Quest').is_used_prereq())

    def test_get_reliant_qs__matches_manager(self):
        """get_reliant_qs returns the same prereqs as the manager's all_reliant_on."""
        reliant = self.quest_prereq.get_reliant_qs()

        self.assertListEqual(list(reliant), list(Prereq.objects.all_reliant_on(self.quest_prereq)))

    def test_get_reliant_objects__returns_parents(self):
        """get_reliant_objects returns every parent that relies on the object."""
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
        """With exclude_NOT, an inverted main requirement drops its parent from the reliant list."""
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

    def test_get_reliant_objects__exclude_NOT__inverted_or_prereq(self):
        """An object that is only an inverted (NOT) alternate requirement of a
        parent must not be reported as having reliant objects when
        exclude_NOT=True. Regression test for issue #1900:
        get_all_for_or_prereq_object discarded its exclude() result, so
        exclude_NOT had no effect for the OR requirement slot."""
        # from setUp: quest_or_prereq is the OR requirement of prereq_with_or,
        # whose parent is quest_parent
        reliant_objects = self.quest_or_prereq.get_reliant_objects(exclude_NOT=True)
        self.assertListEqual(list(reliant_objects), [self.quest_parent])

        # invert the OR requirement (NOT): the parent no longer relies on it
        self.prereq_with_or.or_prereq_invert = True
        self.prereq_with_or.full_clean()
        self.prereq_with_or.save()

        reliant_objects = self.quest_or_prereq.get_reliant_objects(exclude_NOT=True)
        self.assertListEqual(list(reliant_objects), [])

        # without exclude_NOT, the inverted OR relationship is still reported
        reliant_objects = self.quest_or_prereq.get_reliant_objects(exclude_NOT=False)
        self.assertListEqual(list(reliant_objects), [self.quest_parent])

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
            model_class = ct.model_class()
            if model_class is Prereq:
                # baker.make(Prereq) fills the generic foreign keys with a random
                # content type — any installed model, even ones that can't be
                # prereqs, like Portfolio (whose primary key isn't named 'id',
                # crashing the map-regeneration signal on save). This made CI
                # randomly flaky. Build a deterministic Prereq instead.
                instance = Prereq.objects.create(
                    parent_object=baker.make('quest_manager.Quest'),
                    prereq_object=baker.make('quest_manager.Quest'),
                )
            else:
                instance = baker.make(model_class)
            # If the method is not implemented, then NotImplementedError is thrown
            try:
                instance.condition_met_as_prerequisite(user=baker.make(User), num_required=1)
            except UndefinedTable:
                # Ignore unrelated missing table errors from debug toolbar
                # https://github.com/bytedeck/bytedeck/issues/1868
                pass

    def test_gfk_search_fields__is_implemented(self):
        """ All models implementing this Mixin, also implement this method if the default doesn't suffice """
        prereq_models = IsAPrereqMixin.all_registered_model_classes()
        for model in prereq_models:
            assert all(isinstance(x, str) for x in model.gfk_search_fields())

    def test_content_type_is_registered__reflects_registration(self):
        """A content_type representing a model that implements the IsAPrereqMixin returns True
        """
        ct = ContentType.objects.get(app_label='quest_manager', model='quest')
        self.assertTrue(IsAPrereqMixin.content_type_is_registered(ct))

        ct = ContentType.objects.get(app_label='auth', model='user')
        self.assertFalse(IsAPrereqMixin.content_type_is_registered(ct))

    def test_all_registered_content_types__returns_expected_count(self):
        """There are 6 models that implement the IsAPrereqMixin
        """
        cts = IsAPrereqMixin.all_registered_content_types()
        self.assertEqual(cts.count(), 8)

    @isolate_apps('prerequisites')
    def test_model_is_registered__reflects_mixin(self):
        """Any model class that implements IsAPrereqMixin returns True"""
        # isolate_apps keeps these throwaway models out of the global app registry.
        # Otherwise they leak process-wide: their content types get created on the
        # next schema build (so baker.make can pick them for a GFK) and any code
        # that iterates all models (e.g. the full_clean command) queries their
        # non-existent tables -- an order-dependent failure that only shows up when
        # this test runs before those.
        class TestClassRegistered(IsAPrereqMixin, models.Model):
            pass

        class TestClassNotRegsistered(models.Model):
            pass

        self.assertTrue(IsAPrereqMixin.model_is_registered(TestClassRegistered))
        self.assertFalse(IsAPrereqMixin.model_is_registered(TestClassNotRegsistered))


class PrereqModelTest(ByteDeckTenantTestCase):
    @classmethod
    def setUpTestData(cls):
        """Create a student and an unsaved Prereq linking two quests."""
        cls.student = baker.make(User, username='student', is_staff=False)
        cls.quest_parent = baker.make('quest_manager.Quest')
        cls.quest_prereq = baker.make('quest_manager.Quest')
        cls.prereq = Prereq(
            parent_object=cls.quest_parent,
            prereq_object=cls.quest_prereq
        )

    def test_object_creation__is_prereq_instance(self):
        """A built Prereq is an instance of both Prereq and IsAPrereqMixin."""
        self.assertIsInstance(self.prereq, Prereq)
        self.assertIsInstance(self.prereq, IsAPrereqMixin)

    def test_parent__returns_parent_object(self):
        "returns the parent of the prereq"
        self.assertEqual(self.prereq.parent(), self.quest_parent)

    def test_get_prereq__returns_main_requirement(self):
        "returns the main prereq requirement"
        self.assertEqual(self.prereq.get_prereq(), self.quest_prereq)

    def test_get_or_prereq__returns_none_when_unset(self):
        "returns the alternate prereq requirement"
        self.assertIsNone(self.prereq.get_or_prereq())

    # Todo: need some massive mocking for this one
    # @patch('prereq_object.condition_met_as_prerequisite', return_value=True)
    # def test_conditions_met(self, condition_met_as_prerequisite):
    #     print("Call count: ", condition_met_as_prerequisite.call_count)
    #     self.assertTrue(self.prereq.condition_met(self.student))

    def test_add_simple_prereq__creates_reliance(self):
        """add_simple_prereq makes the parent reliant on the given prereq object."""
        quest3 = baker.make('quest_manager.Quest')
        Prereq.add_simple_prereq(self.quest_parent, quest3)
        self.assertIn(self.quest_parent, quest3.get_reliant_objects())

    def test_add_simple_prereq__bad_parent(self):
        """A parent_object that does not implement the HasPrereqsMixin should raise an exception
        """
        with self.assertRaises(TypeError):
            quest3 = baker.make('quest_manager.Quest')
            some_object = object()
            Prereq.add_simple_prereq(some_object, quest3)

    def test_add_simple_prereq__bad_prereq(self):
        """A prereq_object that does not implement the IsAPrereqMixin should raise an exception
        """
        with self.assertRaises(TypeError):
            quest3 = baker.make('quest_manager.Quest')
            some_object = object()
            Prereq.add_simple_prereq(quest3, some_object)


class PrereqAllConditionsMetModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a student and a PrereqAllConditionsMet cache for them."""
        cls.student = baker.make(User, username='student', is_staff=False)
        cls.prereq_cache = baker.make(
            PrereqAllConditionsMet,
            user=cls.student,
            model_name='fake_model_name'
        )

    def test_object_creation__defaults(self):
        """A new cache object stores its user and defaults ids to an empty list."""
        self.assertIsInstance(self.prereq_cache, PrereqAllConditionsMet)
        self.assertEqual(self.prereq_cache.user, self.student)
        self.assertEqual(self.prereq_cache.ids, '[]')

    def test_duplicate_user_and_model_name__not_allowed(self):
        """Only one cache object can exist per user per model. Duplicate cache
        objects caused `get()` and `update_or_create()` in the celery tasks to
        raise MultipleObjectsReturned. Regression test for issue #520.
        """
        with self.assertRaises(IntegrityError):
            PrereqAllConditionsMet.objects.create(
                user=self.student,
                model_name='fake_model_name'
            )

    def test_get_ids__empty(self):
        """get_ids returns an empty list when no ids are stored."""
        self.assertEqual([], self.prereq_cache.get_ids())

    def test_get_ids__returns_stored_ids(self):
        """get_ids parses the stored string back into a list of ids."""
        ids = [1, 2, 3, 4, 5]
        self.prereq_cache.ids = str(ids)
        self.assertEqual(ids, self.prereq_cache.get_ids())

    def test_add_id__appends(self):
        """add_id appends new ids to the cache in order."""
        self.assertEqual(len(self.prereq_cache.get_ids()), 0)

        self.prereq_cache.add_id(100)
        self.assertEqual(len(self.prereq_cache.get_ids()), 1)
        self.assertEqual(self.prereq_cache.get_ids(), [100])

        self.prereq_cache.add_id(101)
        self.assertEqual(len(self.prereq_cache.get_ids()), 2)
        self.assertEqual(self.prereq_cache.get_ids(), [100, 101])

    def test_remove_id__removes(self):
        """remove_id deletes an existing id from the cache."""
        self.prereq_cache.ids = str([1, 2, 3, 4, 5])
        self.assertIn(1, self.prereq_cache.get_ids())

        self.prereq_cache.remove_id(1)
        self.assertNotIn(1, self.prereq_cache.get_ids())

    def test_remove_id__nonexistent_is_noop(self):
        """Removing an id that isn't stored leaves the cache unchanged."""
        ids = [1, 2, 3, 4, 5]
        self.prereq_cache.ids = str(ids)
        self.assertNotIn(6, self.prereq_cache.get_ids())

        self.prereq_cache.remove_id(6)
        self.assertNotIn(6, self.prereq_cache.get_ids())
        self.assertEqual(len(self.prereq_cache.get_ids()), len(ids))


class AddSimplePrereqAllRegisteredModelsTest(ByteDeckTenantTestCase):
    """Prereq.add_simple_prereq must work for every registered prereq model —
    the models that implement IsAPrereqMixin, which are the only models that
    are supposed to be used in a Prereq's generic foreign keys."""

    def test_add_simple_prereq__for_every_registered_model(self):
        """Loops through all registered prereq models, using each as the
        requirement of a new Prereq, and checks the stored generic ids."""
        parent = baker.make('quest_manager.Quest')
        for model_class in IsAPrereqMixin.all_registered_model_classes():
            with self.subTest(prereq_model=model_class.__name__):
                if model_class is Prereq:
                    # baker.make(Prereq) would pick random content types;
                    # build a deterministic one instead
                    prereq_object = Prereq.add_simple_prereq(
                        baker.make('quest_manager.Quest'), baker.make('quest_manager.Quest'))
                elif model_class.__name__ == 'Rank':
                    # a Rank prereq triggers map generation (see
                    # prerequisites.signals), which requires a non-blank name
                    prereq_object = baker.make(model_class, name='Test Rank')
                else:
                    prereq_object = baker.make(model_class)
                new_prereq = Prereq.add_simple_prereq(parent, prereq_object)
                self.assertEqual(new_prereq.parent_object_id, parent.pk)
                self.assertEqual(new_prereq.prereq_object_id, prereq_object.pk)
                self.assertEqual(new_prereq.get_prereq(), prereq_object)


class PrereqPrefetchTest(ByteDeckTenantTestCase):
    """PrereqManager.prefetch_for_parents batches prereqs() for many same-model
    objects into a single query (used by the profile page's badge popovers)."""

    @classmethod
    def setUpTestData(cls):
        """Create two parent quests sharing one prereq requirement."""
        cls.parent1 = baker.make('quest_manager.Quest')
        cls.parent2 = baker.make('quest_manager.Quest')
        cls.requirement = baker.make('quest_manager.Quest')
        Prereq.add_simple_prereq(cls.parent1, cls.requirement)
        Prereq.add_simple_prereq(cls.parent2, cls.requirement)

    def test_prereqs__without_prefetch_returns_queryset(self):
        """Objects that were not prefetched keep the normal queryset API."""
        from quest_manager.models import Quest
        quest = Quest.objects.get(pk=self.parent1.pk)
        self.assertEqual(quest.prereqs().count(), 1)
        self.assertTrue(quest.prereqs().exists())

    def test_prefetch_for_parents__serves_prereqs_without_per_object_queries(self):
        """After prefetch_for_parents, each object's prereqs() is served from
        its cache with no further per-object query."""
        from quest_manager.models import Quest
        quests = list(Quest.objects.filter(pk__in=[self.parent1.pk, self.parent2.pk]))

        Prereq.objects.prefetch_for_parents(quests)

        with self.assertNumQueries(0):
            for quest in quests:
                prereqs = quest.prereqs()
                self.assertEqual(len(list(prereqs)), 1)
                self.assertEqual(prereqs[0].parent_object_id, quest.pk)

    def test_prefetch_for_parents__empty_input(self):
        """Empty input is a no-op returning an empty list (no query)."""
        with self.assertNumQueries(0):
            self.assertEqual(Prereq.objects.prefetch_for_parents([]), [])

    def test_prefetch_for_parents__rejects_mixed_models(self):
        """Mixed-model input is rejected: all parents must share one content
        type, or the query would silently drop some objects' prereqs."""
        badge = baker.make('badges.Badge')
        with self.assertRaises(ValueError):
            Prereq.objects.prefetch_for_parents([self.parent1, badge])


class PrereqStrAndConditionMetTest(ByteDeckTenantTestCase):
    """Covers Prereq.__str__ formatting and the branches of Prereq.condition_met."""

    @classmethod
    def setUpTestData(cls):
        """Create a parent quest plus a main and an alternate (OR) prereq quest, and a user."""
        cls.parent = baker.make('quest_manager.Quest', name="parent")
        cls.main = baker.make('quest_manager.Quest', name="main")
        cls.alt = baker.make('quest_manager.Quest', name="alt")
        cls.user = baker.make(User)

    def test_str__renders_not_or_and_repeat_counts(self):
        """__str__ shows NOT (invert), OR (alternate) and xN (counts > 1) for a full prereq."""
        prereq = Prereq.objects.create(
            parent_object=self.parent,
            prereq_object=self.main,
            or_prereq_object=self.alt,
            prereq_invert=True,
            or_prereq_invert=True,
            prereq_count=2,
            or_prereq_count=3,
        )
        rendered = str(prereq)
        self.assertIn("NOT", rendered)
        self.assertIn("OR", rendered)
        self.assertIn("x2", rendered)
        self.assertIn("x3", rendered)

    def test_str__renders_plain_or_without_not_or_counts(self):
        """A non-inverted OR prereq with single counts renders no NOT/xN, just the OR."""
        prereq = Prereq.objects.create(
            parent_object=self.parent,
            prereq_object=self.main,
            or_prereq_object=self.alt,
        )
        rendered = str(prereq)
        self.assertNotIn("NOT", rendered)
        self.assertIn("OR", rendered)
        self.assertNotIn("x", rendered)

    def test_condition_met__non_inverted_or_alternate_not_met_returns_false(self):
        """A plain (non-inverted) OR alternate the user hasn't met leaves the condition unmet."""
        prereq = Prereq.objects.create(
            parent_object=self.parent,
            prereq_object=self.main,
            or_prereq_object=self.alt,
        )
        # Neither main nor OR alternate completed, neither inverted -> not met.
        self.assertFalse(prereq.condition_met(self.user))

    def test_condition_met__inverted_main_is_true_when_user_lacks_it(self):
        """An inverted (NOT) main requirement is met when the user has NOT completed it."""
        prereq = Prereq.objects.create(parent_object=self.parent, prereq_object=self.main, prereq_invert=True)
        # The user has no approved submissions, so the main condition is False; inverted -> True.
        self.assertTrue(prereq.condition_met(self.user))

    def test_condition_met__missing_main_prereq_object_returns_false(self):
        """If the main prereq object no longer exists, the condition is not met."""
        prereq = Prereq.objects.create(parent_object=self.parent, prereq_object=self.main)
        # Point the GFK at a non-existent id via update() (bypasses the delete-cascade signal
        # that would otherwise remove the Prereq row), then reload a fresh instance so the GFK
        # re-resolves to None.
        Prereq.objects.filter(pk=prereq.pk).update(prereq_object_id=99999999)
        prereq = Prereq.objects.get(pk=prereq.pk)
        self.assertFalse(prereq.condition_met(self.user))

    def test_condition_met__or_requirement_met_via_invert(self):
        """When the main is unmet but the inverted OR alternate is met, the condition passes."""
        prereq = Prereq.objects.create(
            parent_object=self.parent,
            prereq_object=self.main,
            or_prereq_object=self.alt,
            or_prereq_invert=True,
        )
        # main (self.main) not completed -> False; OR alternate inverted and not completed -> True.
        self.assertTrue(prereq.condition_met(self.user))

    def test_condition_met__missing_or_prereq_object_returns_false(self):
        """A dangling OR alternate (object deleted) makes the condition not met."""
        prereq = Prereq.objects.create(
            parent_object=self.parent,
            prereq_object=self.main,
            or_prereq_object=self.alt,
        )
        # Dangle the OR alternate at a non-existent id (see the main-prereq test for why update()).
        Prereq.objects.filter(pk=prereq.pk).update(or_prereq_object_id=99999999)
        prereq = Prereq.objects.get(pk=prereq.pk)
        self.assertFalse(prereq.condition_met(self.user))


class PrereqManagerIsPrerequisiteTest(ByteDeckTenantTestCase):
    """Covers PrereqManager.is_prerequisite for the OR-prereq branch."""

    def test_is_prerequisite__true_for_object_used_only_as_or_prereq(self):
        """An object used solely as an OR alternate is still recognised as a prerequisite."""
        parent = baker.make('quest_manager.Quest')
        main = baker.make('quest_manager.Quest')
        or_only = baker.make('quest_manager.Quest')
        Prereq.objects.create(parent_object=parent, prereq_object=main, or_prereq_object=or_only)

        # or_only is not a main prereq anywhere, so the first lookup misses and the OR lookup matches.
        self.assertTrue(Prereq.objects.is_prerequisite(or_only))


class PrereqAllConditionsMetIdsTest(ByteDeckTenantTestCase):
    """Covers PrereqAllConditionsMet.get_ids / set_ids, including the empty-ids branch (a former bug)."""

    def setUp(self):
        """Create a PrereqAllConditionsMet cache row for a fresh user and the Quest model."""
        self.cache = PrereqAllConditionsMet.objects.create(
            user=baker.make(User),
            model_name='quest_manager.Quest',
        )

    def test_get_ids__blank_ids_returns_empty_list(self):
        """Blank ``ids`` returns an empty list (previously raised AttributeError)."""
        self.cache.ids = ''
        self.assertEqual(self.cache.get_ids(), [])

    def test_set_ids__none_defaults_to_empty_list(self):
        """Calling set_ids() with no argument stores an empty list."""
        self.cache.set_ids(None)
        self.cache.refresh_from_db()
        self.assertEqual(self.cache.get_ids(), [])

    def test_get_ids__parses_stored_list(self):
        """A populated ``ids`` string is parsed back into a list of ids."""
        self.cache.set_ids([25, 34, 55])
        self.cache.refresh_from_db()
        self.assertEqual(self.cache.get_ids(), [25, 34, 55])
