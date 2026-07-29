import uuid

from django.contrib import admin as django_admin
from django.contrib.auth import get_user_model

import tablib
from model_bakery import baker

from badges.admin import (
    BADGE_EXPORT_EXCLUDED_HTML_FIELDS,
    BadgeAdmin,
    BadgeAdminExportResource,
    BadgeResource,
)
from badges.models import Badge, BadgeType
from hackerspace_online.tests.utils import ByteDeckTenantTestCase, request_with_messages
from prerequisites.models import Prereq
from quest_manager.models import Category, Quest

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

    def test_dehydrate_prereq_import_ids__skips_non_quest_or_badge_prereqs(self):
        """Prereqs that aren't quests or badges (e.g. a campaign) aren't exportable and are skipped."""
        badge = baker.make(Badge)
        campaign = baker.make(Category)
        Prereq.add_simple_prereq(badge, campaign)

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

    def test_generate_simple_prereqs__unknown_import_id_adds_nothing(self):
        """An import_id matching neither a quest nor a badge is silently skipped."""
        parent = baker.make(Badge)
        data_dict = {'prereq_import_ids': '&' + str(uuid.uuid4())}

        self.resource.generate_simple_prereqs(parent, data_dict)

        self.assertEqual(len(parent.prereqs()), 0)


class BadgeResourceAfterImportTest(ByteDeckTenantTestCase):
    """Tests for BadgeResource.after_import, which rebuilds prereqs once a real import commits."""

    def setUp(self):
        """Build a fresh BadgeResource and a dataset carrying one badge + a quest prereq import_id."""
        self.resource = BadgeResource()
        self.parent = baker.make(Badge)
        self.prereq_quest = baker.make(Quest)
        self.dataset = tablib.Dataset(headers=['import_id', 'prereq_import_ids'])
        self.dataset.append([str(self.parent.import_id), '&' + str(self.prereq_quest.import_id)])

    def test_after_import__generates_prereqs_on_real_import(self):
        """On a committed import (dry_run=False) the row's prereq import_ids become real prereqs."""
        self.resource.after_import(self.dataset, None, dry_run=False)

        self.assertIn(self.prereq_quest, [p.get_prereq() for p in self.parent.prereqs()])

    def test_after_import__skips_prereq_generation_during_dry_run(self):
        """During the dry-run/preview step (dry_run=True) no prereqs are created."""
        self.resource.after_import(self.dataset, None, dry_run=True)

        self.assertEqual(len(self.parent.prereqs()), 0)


class BadgeAdminFormatsTest(ByteDeckTenantTestCase):
    """Tests that BadgeAdmin restricts import/export to CSV."""

    def test_get_import_formats__csv_only(self):
        """Importing is restricted to CSV."""
        modeladmin = BadgeAdmin(Badge, django_admin.site)
        formats = modeladmin.get_import_formats()
        self.assertEqual([fmt().get_title() for fmt in formats], ['csv'])

    def test_get_export_formats__csv_only(self):
        """Exporting is restricted to CSV."""
        modeladmin = BadgeAdmin(Badge, django_admin.site)
        formats = modeladmin.get_export_formats()
        self.assertEqual([fmt().get_title() for fmt in formats], ['csv'])


class BadgeAdminExportResourceTest(ByteDeckTenantTestCase):
    """The admin Export button drops the bulky HTML columns to bound per-request memory
    (#2081); the full BadgeResource (import / Shared Library) keeps them."""

    def test_admin_export_resource__omits_bulky_html_columns(self):
        """BadgeAdminExportResource's export has no short_description column."""
        badge = baker.make(Badge, short_description='<p>lots of html</p>')

        headers = BadgeAdminExportResource().export([badge]).headers

        for field in BADGE_EXPORT_EXCLUDED_HTML_FIELDS:
            self.assertNotIn(field, headers)
        # Identifying/lightweight columns are still exported.
        self.assertIn('name', headers)

    def test_full_resource__still_exports_short_description(self):
        """The full BadgeResource still carries the HTML field for import / sharing."""
        badge = baker.make(Badge, short_description='<p>keep me</p>')

        self.assertIn('short_description', BadgeResource().export([badge]).headers)

    def test_badge_admin__export_uses_slim_resource_import_uses_full(self):
        """BadgeAdmin exports with the slim resource but imports with the full one."""
        modeladmin = BadgeAdmin(Badge, django_admin.site)
        request = request_with_messages()

        self.assertEqual(modeladmin.get_export_resource_classes(request), [BadgeAdminExportResource])
        self.assertEqual(modeladmin.get_import_resource_classes(request), [BadgeResource])
