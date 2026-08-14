from django.test import SimpleTestCase

from library.resources import LibraryQuestResource
from library.tests.test_views import LibraryTenantTestCaseMixin
from library.utils import library_schema_context
from model_bakery import baker
from quest_manager.admin import QUEST_EXPORT_EXCLUDED_HTML_FIELDS, QuestAdminExportResource, QuestResource
from quest_manager.models import Quest


class LibraryQuestResourceTest(SimpleTestCase):
    """The Library's serialization contract, as distinct from the admin's.

    These are the properties the cross-deck sharing feature depends on, pinned here in the
    library app so that a change to the admin's CSV export can't quietly take them away
    (#2378).
    """

    def test_LibraryQuestResource__exports_the_full_quest_content(self):
        """The Library carries the summernote HTML fields the admin's export drops.

        The admin export omits them on purpose, to bound the memory a table dump costs
        (#2081). A quest shared to the Library without its instructions would not be the
        quest, so the Library's resource must keep exporting them.
        """
        library_columns = [field.column_name for field in LibraryQuestResource().get_export_fields()]
        admin_columns = [field.column_name for field in QuestAdminExportResource().get_export_fields()]

        for column in QUEST_EXPORT_EXCLUDED_HTML_FIELDS:
            self.assertIn(column, library_columns)
            self.assertNotIn(column, admin_columns)

    def test_LibraryQuestResource__does_not_export_the_local_only_fields(self):
        """Fields whose values mean something different in another schema stay behind.

        `editor` and `specific_teacher_to_notify` are local user ids and `common_data` a
        local row id, so carrying them across decks would point the imported quest at
        whoever happens to hold those ids there.
        """
        columns = [field.column_name for field in LibraryQuestResource().get_export_fields()]

        for column in ('id', 'editor', 'specific_teacher_to_notify', 'common_data'):
            self.assertNotIn(column, columns)

    def test_LibraryQuestResource__visibility_map_is_per_instance(self):
        """Each resource starts with its own empty visibility map.

        The map is what preserves a deck's own published/unpublished choice when it
        re-imports a quest it already has, and it is filled in per import. Were the empty
        default shared between instances, one import could be read as another's default.
        """
        first, second = LibraryQuestResource(), LibraryQuestResource()

        first.local_visibility_map['some-import-id'] = True

        self.assertEqual(second.local_visibility_map, {})
        # and the class itself is not carrying the state either
        self.assertFalse(hasattr(QuestResource, 'local_visibility_map'))


class LibraryQuestResourceRoundTripTest(LibraryTenantTestCaseMixin):
    """What actually survives a trip through the Library's serialization."""

    def test_LibraryQuestResource__round_trip_keeps_the_quest_content(self):
        """Exporting a quest in one schema and importing it in another keeps its content.

        This is the property the whole feature rests on: the deck that imports a quest
        gets the instructions, submission details and instructor notes that the deck which
        shared it wrote.
        """
        content = {
            'instructions': '<p>Do the thing, then <b>show your work</b>.</p>',
            'submission_details': '<p>Paste a link to your repository.</p>',
            'instructor_notes': '<p>Watch for the off-by-one.</p>',
        }
        with library_schema_context():
            baker.make(Quest, name='A quest worth importing', published=True, **content)
            export_data = LibraryQuestResource().export(Quest.objects.filter(name='A quest worth importing'))

        # back on the deck's own schema, which is where a real import lands
        LibraryQuestResource().import_data(export_data, dry_run=False, raise_errors=True)

        imported = Quest.objects.get(name='A quest worth importing')
        # compared by their text, not byte for byte: saving a quest re-indents its HTML
        expected_text = {
            'instructions': 'Do the thing, then <b>show your work</b>.',
            'submission_details': 'Paste a link to your repository.',
            'instructor_notes': 'Watch for the off-by-one.',
        }
        for field, text in expected_text.items():
            self.assertIn(text, ' '.join(getattr(imported, field).split()))
