from django.contrib.auth import get_user_model

from model_bakery import baker

from badges.admin import BadgeResource
from badges.models import Badge, BadgeType
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from prerequisites.models import Prereq
from quest_manager.models import Quest

User = get_user_model()


class BadgeResourceDehydrateTest(ByteDeckTenantTestCase):
    """Tests for BadgeResource's dehydrate_* export helpers."""

    def setUp(self):
        """Build a fresh BadgeResource for each test."""
        self.resource = BadgeResource()

    def test_dehydrate_badge_type_fields__return_none_before_badge_saved(self):
        """During import, dehydrate runs once on an unsaved badge (no id); those calls return None."""
        unsaved = Badge()  # no pk
        self.assertIsNone(self.resource.dehydrate_badge_type_name(unsaved))
        self.assertIsNone(self.resource.dehydrate_badge_type_sort(unsaved))
        self.assertIsNone(self.resource.dehydrate_badge_type_icon(unsaved))

    def test_dehydrate_badge_type_fields__return_type_attributes_for_saved_badge(self):
        """For a saved badge the helpers surface its badge type's name, sort order and icon."""
        badge_type = baker.make(BadgeType, name='Gold', sort_order=3, fa_icon='fa-star')
        badge = baker.make(Badge, badge_type=badge_type)

        self.assertEqual(self.resource.dehydrate_badge_type_name(badge), str(badge_type))
        self.assertEqual(self.resource.dehydrate_badge_type_sort(badge), 3)
        self.assertEqual(self.resource.dehydrate_badge_type_icon(badge), 'fa-star')

    def test_dehydrate_prereq_import_ids__lists_quest_and_badge_prereqs(self):
        """The exported prereq string is an &-joined list of prerequisite import_ids."""
        badge = baker.make(Badge)
        quest_prereq = baker.make(Quest)
        badge_prereq = baker.make(Badge)
        Prereq.add_simple_prereq(badge, quest_prereq)
        Prereq.add_simple_prereq(badge, badge_prereq)

        result = self.resource.dehydrate_prereq_import_ids(badge)

        self.assertIn(str(quest_prereq.import_id), result)
        self.assertIn(str(badge_prereq.import_id), result)

    def test_dehydrate_prereq_import_ids__empty_when_no_prereqs(self):
        """A badge with no prerequisites exports an empty prereq string."""
        badge = baker.make(Badge)
        self.assertEqual(self.resource.dehydrate_prereq_import_ids(badge), '')


class BadgeResourceGenerateBadgeTypeTest(ByteDeckTenantTestCase):
    """Tests for BadgeResource.generate_badge_type, which resolves/creates a BadgeType during import."""

    def setUp(self):
        """Build a fresh BadgeResource for each test."""
        self.resource = BadgeResource()

    def test_generate_badge_type__creates_badge_type_and_sets_row(self):
        """A row naming a new badge type creates it and rewrites row['badge_type'] to its id."""
        row = {'badge_type_name': 'Platinum', 'badge_type_sort': 5, 'badge_type_icon': 'fa-gem'}

        self.resource.generate_badge_type(row)

        badge_type = BadgeType.objects.get(name='Platinum')
        self.assertEqual(row['badge_type'], badge_type.id)
        self.assertEqual(badge_type.sort_order, 5)
        self.assertEqual(badge_type.fa_icon, 'fa-gem')

    def test_generate_badge_type__reuses_existing_badge_type(self):
        """An existing badge type of the same name is reused rather than duplicated."""
        existing = baker.make(BadgeType, name='Silver')
        row = {'badge_type_name': 'Silver', 'badge_type_sort': None, 'badge_type_icon': None}

        self.resource.generate_badge_type(row)

        self.assertEqual(row['badge_type'], existing.id)
        self.assertEqual(BadgeType.objects.filter(name='Silver').count(), 1)

    def test_generate_badge_type__no_name_is_a_noop(self):
        """A row without a badge type name leaves the row untouched and creates nothing."""
        before = BadgeType.objects.count()
        row = {'badge_type_name': '', 'badge_type_sort': 1, 'badge_type_icon': 'fa-x'}

        self.resource.generate_badge_type(row)

        self.assertNotIn('badge_type', row)
        self.assertEqual(BadgeType.objects.count(), before)

    def test_before_import_row__delegates_to_generate_badge_type(self):
        """before_import_row creates the badge type for the row being imported."""
        row = {'badge_type_name': 'Bronze', 'badge_type_sort': 2, 'badge_type_icon': 'fa-medal'}
        self.resource.before_import_row(row)
        self.assertTrue(BadgeType.objects.filter(name='Bronze').exists())


class BadgeResourceGenerateSimplePrereqsTest(ByteDeckTenantTestCase):
    """Tests for BadgeResource.generate_simple_prereqs, which recreates prereqs during import."""

    def setUp(self):
        """Build a fresh BadgeResource for each test."""
        self.resource = BadgeResource()

    def test_generate_simple_prereqs__creates_prereq_from_quest_import_id(self):
        """A prereq import_id pointing at an existing quest becomes a simple prereq of the parent."""
        parent = baker.make(Badge)
        quest_prereq = baker.make(Quest)
        data_dict = {'prereq_import_ids': f'&{quest_prereq.import_id}'}

        self.resource.generate_simple_prereqs(parent, data_dict)

        self.assertEqual(len(parent.prereqs()), 1)

    def test_generate_simple_prereqs__creates_prereq_from_badge_import_id(self):
        """A prereq import_id pointing at an existing badge (not a quest) also works."""
        parent = baker.make(Badge)
        badge_prereq = baker.make(Badge)
        data_dict = {'prereq_import_ids': f'&{badge_prereq.import_id}'}

        self.resource.generate_simple_prereqs(parent, data_dict)

        self.assertEqual(len(parent.prereqs()), 1)

    def test_generate_simple_prereqs__does_not_duplicate_existing_prereq(self):
        """An import_id already present as a prereq is not added a second time."""
        parent = baker.make(Badge)
        quest_prereq = baker.make(Quest)
        Prereq.add_simple_prereq(parent, quest_prereq)
        data_dict = {'prereq_import_ids': f'&{quest_prereq.import_id}'}

        self.resource.generate_simple_prereqs(parent, data_dict)

        self.assertEqual(len(parent.prereqs()), 1)

    def test_generate_simple_prereqs__blank_import_ids_add_nothing(self):
        """A blank prereq import_ids string adds no prerequisites."""
        parent = baker.make(Badge)
        data_dict = {'prereq_import_ids': ''}

        self.resource.generate_simple_prereqs(parent, data_dict)

        self.assertEqual(len(parent.prereqs()), 0)
