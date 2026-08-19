import json

from django.core.exceptions import ValidationError

from django_tenants.test.cases import TenantTestCase
from model_bakery import baker

from competencies.import_export import (
    export_competency_set,
    export_csv,
    get_bundled_set_keys,
    import_competency_set,
    load_bundled_set,
    parse_csv_set,
    parse_json_set,
    preview_entry_statuses,
    validate_competency_set,
)
from competencies.models import Competency


def make_set(entries, **metadata):
    """ A minimal raw competency-set dict for tests """
    data = {
        'format': 'bytedeck-competency-set',
        'version': 1,
        'name': 'Test Set',
        'entries': entries,
    }
    data.update(metadata)
    return data


def make_valid_set(entries, **metadata):
    """ A normalized competency set, as the import functions expect """
    return validate_competency_set(make_set(entries, **metadata))


class ParseAndValidateTest(TenantTestCase):
    """ Tests for the JSON/CSV competency-set parsers and the set validator. """

    def test_parse_json_set__happy_path(self):
        """ A well-formed JSON set parses into normalized metadata and entries """
        raw = json.dumps(make_set(
            [{'source_id': 'x:1', 'name': 'Think', 'description': 'desc', 'category': 'Thinking'}],
            jurisdiction='BC', subject='Math', grade='8', source_url='https://example.com',
        ))
        competency_set = parse_json_set(raw)

        self.assertEqual(competency_set['name'], 'Test Set')
        self.assertEqual(competency_set['jurisdiction'], 'BC')
        self.assertEqual(competency_set['entries'], [
            {'source_id': 'x:1', 'name': 'Think', 'description': 'desc', 'category': 'Thinking'}
        ])

    def test_parse_json_set__malformed_json(self):
        """ Malformed JSON is rejected with a ValidationError """
        with self.assertRaises(ValidationError):
            parse_json_set("{not valid json")

    def test_parse_json_set__not_utf8(self):
        """ Bytes that aren't UTF-8 text are rejected with a ValidationError """
        with self.assertRaises(ValidationError):
            parse_json_set(b'\xff\xfe\x00broken')

    def test_parse_json_set__wrong_format_marker(self):
        """ JSON without the bytedeck-competency-set format marker is rejected """
        with self.assertRaises(ValidationError):
            parse_json_set(json.dumps({'format': 'something-else', 'version': 1, 'entries': [{'name': 'x'}]}))

    def test_parse_json_set__unsupported_version(self):
        """ A version newer than this deck supports is rejected """
        with self.assertRaises(ValidationError):
            parse_json_set(json.dumps(make_set([{'name': 'x'}], version=99)))

    def test_parse_json_set__no_entries(self):
        """ A set with an empty entries list is rejected """
        with self.assertRaises(ValidationError):
            parse_json_set(json.dumps(make_set([])))

    def test_parse_json_set__entry_missing_name(self):
        """ An entry with a blank name is rejected """
        with self.assertRaises(ValidationError):
            parse_json_set(json.dumps(make_set([{'source_id': 'x:1', 'name': '  '}])))

    def test_parse_json_set__duplicate_source_ids(self):
        """ Two entries sharing a source_id are rejected """
        with self.assertRaises(ValidationError):
            parse_json_set(json.dumps(make_set([
                {'source_id': 'x:1', 'name': 'a'},
                {'source_id': 'x:1', 'name': 'b'},
            ])))

    def test_parse_csv_set__happy_path(self):
        """ A well-formed CSV parses; missing optional cells become empty strings """
        raw = (
            "name,category,description,source_id\n"
            "Think critically,Thinking,A description,x:1\n"
            "Communicate,,,\n"
        )
        competency_set = parse_csv_set(raw, name='my-set')

        self.assertEqual(competency_set['name'], 'my-set')
        self.assertEqual(len(competency_set['entries']), 2)
        self.assertEqual(competency_set['entries'][0], {
            'name': 'Think critically', 'category': 'Thinking', 'description': 'A description', 'source_id': 'x:1',
        })
        self.assertEqual(competency_set['entries'][1]['name'], 'Communicate')
        self.assertEqual(competency_set['entries'][1]['source_id'], '')

    def test_parse_csv_set__column_order_does_not_matter(self):
        """ CSV columns are matched by header name, not position """
        competency_set = parse_csv_set("category,name\nThinking,Think\n")
        self.assertEqual(competency_set['entries'][0]['name'], 'Think')
        self.assertEqual(competency_set['entries'][0]['category'], 'Thinking')

    def test_parse_csv_set__tolerates_excel_bom_and_blank_lines(self):
        """ An Excel-style UTF-8 BOM and fully blank rows are tolerated """
        raw = b'\xef\xbb\xbfname,category\r\nThink,Thinking\r\n,\r\n'
        competency_set = parse_csv_set(raw)
        self.assertEqual(len(competency_set['entries']), 1)

    def test_parse_csv_set__missing_name_column(self):
        """ A CSV without a name column is rejected """
        with self.assertRaises(ValidationError):
            parse_csv_set("title,category\nThink,Thinking\n")

    def test_parse_csv_set__unknown_column(self):
        """ A CSV with an unrecognized column is rejected """
        with self.assertRaises(ValidationError):
            parse_csv_set("name,level\nThink,3\n")

    def test_parse_csv_set__row_missing_name_value(self):
        """ A CSV row with an empty name cell is rejected """
        with self.assertRaises(ValidationError):
            parse_csv_set("name,category\n,Thinking\n")


class BundledSetsTest(TenantTestCase):
    """ Tests for the curriculum datasets bundled in the app's data/ directory. """

    def test_bundled_sets_exist_and_are_valid(self):
        """ Every dataset bundled in data/ parses and validates """
        keys = get_bundled_set_keys()
        self.assertIn('bc-core-competencies', keys)
        self.assertIn('bc-adst-8', keys)
        self.assertIn('bc-math-8', keys)

        for key in keys:
            competency_set = load_bundled_set(key)  # raises if invalid
            self.assertTrue(competency_set['name'])
            self.assertTrue(competency_set['entries'])
            # bundled curriculum entries all carry a stable source_id for re-import de-dup
            for entry in competency_set['entries']:
                self.assertTrue(entry['source_id'], f"{key}: entry {entry['name']} is missing a source_id")

    def test_load_bundled_set__unknown_key(self):
        """ Asking for a bundled set that doesn't exist raises a ValidationError """
        with self.assertRaises(ValidationError):
            load_bundled_set('no-such-set')

    def test_load_bundled_set__rejects_path_traversal(self):
        """ A path-traversal key can't escape the bundled data directory """
        with self.assertRaises(ValidationError):
            load_bundled_set('../secrets')


class ImportCompetencySetTest(TenantTestCase):
    """ Tests for import_competency_set and the entry-matching rules it applies. """

    def test_import__happy_path(self):
        """ Importing a bundled set into an empty deck creates every entry """
        competency_set = load_bundled_set('bc-core-competencies')
        created, updated = import_competency_set(competency_set)

        self.assertEqual(created, len(competency_set['entries']))
        self.assertEqual(updated, 0)
        self.assertEqual(Competency.objects.count(), created)

        communicating = Competency.objects.get(source_id='bc:core:k-12:communicating')
        self.assertEqual(communicating.name, 'Communicating')
        self.assertEqual(communicating.category, 'Communication')
        self.assertTrue(communicating.active)

    def test_import__reimport_is_idempotent(self):
        """ Re-importing the same set updates in place and never duplicates """
        competency_set = load_bundled_set('bc-core-competencies')
        import_competency_set(competency_set)
        count_after_first = Competency.objects.count()

        created, updated = import_competency_set(competency_set)

        self.assertEqual(created, 0)
        self.assertEqual(updated, count_after_first)
        self.assertEqual(Competency.objects.count(), count_after_first)

    def test_import__reimport_updates_changed_fields(self):
        """ A re-import with changed fields updates the existing competency in place """
        import_competency_set(make_valid_set([{'source_id': 'x:1', 'name': 'Old name', 'category': 'Old'}]))
        import_competency_set(make_valid_set([{'source_id': 'x:1', 'name': 'New name', 'category': 'New', 'description': 'd'}]))

        competency = Competency.objects.get(source_id='x:1')
        self.assertEqual(competency.name, 'New name')
        self.assertEqual(competency.category, 'New')
        self.assertEqual(competency.description, 'd')
        self.assertEqual(Competency.objects.count(), 1)

    def test_import__reimport_leaves_active_flag_alone(self):
        """ A deck's decision to deactivate a competency survives re-import """
        import_competency_set(make_valid_set([{'source_id': 'x:1', 'name': 'Think'}]))
        Competency.objects.filter(source_id='x:1').update(active=False)

        import_competency_set(make_valid_set([{'source_id': 'x:1', 'name': 'Think'}]))
        self.assertFalse(Competency.objects.get(source_id='x:1').active)

    def test_import__source_id_entry_adopts_matching_unsourced_competency(self):
        """ A curriculum import attaches its source_id to a hand-typed competency
        of the same name instead of duplicating it """
        hand_typed = baker.make(Competency, name='Estimate reasonably', source_id=None)

        created, updated = import_competency_set(make_valid_set(
            [{'source_id': 'bc:math:8:reasoning-3', 'name': 'Estimate reasonably'}]
        ))

        self.assertEqual((created, updated), (0, 1))
        hand_typed.refresh_from_db()
        self.assertEqual(hand_typed.source_id, 'bc:math:8:reasoning-3')

    def test_import__same_name_in_other_taxonomy_entry_is_not_hijacked(self):
        """ The same wording under a different source_id (e.g. another grade's set)
        creates a separate competency """
        baker.make(Competency, name='Estimate reasonably', source_id='bc:math:6:reasoning-3')

        created, updated = import_competency_set(make_valid_set(
            [{'source_id': 'bc:math:8:reasoning-3', 'name': 'Estimate reasonably'}]
        ))

        self.assertEqual((created, updated), (1, 0))
        self.assertEqual(Competency.objects.filter(name='Estimate reasonably').count(), 2)

    def test_import__csv_entries_without_source_id_are_idempotent_by_name(self):
        """ Entries without a source_id match existing competencies by name on re-import """
        competency_set = parse_csv_set("name,category\nThink,Thinking\n")
        import_competency_set(competency_set)
        created, updated = import_competency_set(competency_set)

        self.assertEqual((created, updated), (0, 1))
        self.assertEqual(Competency.objects.count(), 1)

    def test_import__selected_indexes_only(self):
        """ Only the selected entry indexes are imported; out-of-range indexes are ignored """
        competency_set = make_valid_set([
            {'source_id': 'x:1', 'name': 'a'},
            {'source_id': 'x:2', 'name': 'b'},
            {'source_id': 'x:3', 'name': 'c'},
        ])
        created, _updated = import_competency_set(competency_set, selected_indexes=[0, 2, 99])

        self.assertEqual(created, 2)
        self.assertEqual(set(Competency.objects.values_list('name', flat=True)), {'a', 'c'})

    def test_preview_entry_statuses(self):
        """ The preview marks entries as update or create depending on whether a match exists """
        baker.make(Competency, name='Existing', source_id='x:1')
        entries = preview_entry_statuses(make_valid_set([
            {'source_id': 'x:1', 'name': 'Existing'},
            {'source_id': 'x:2', 'name': 'Brand new'},
        ]))
        self.assertEqual([e['status'] for e in entries], ['update', 'create'])


class ExportRoundTripTest(TenantTestCase):
    """ Tests for the exporters and full export-import round trips. """

    def test_export__active_competencies_only(self):
        """ The default export includes active competencies and skips deactivated ones """
        baker.make(Competency, name='Active one', active=True)
        baker.make(Competency, name='Retired one', active=False)

        competency_set = export_competency_set()
        names = [e['name'] for e in competency_set['entries']]
        self.assertIn('Active one', names)
        self.assertNotIn('Retired one', names)

    def test_export_import_round_trip__json(self):
        """ Export from one deck, import into another: source_ids, names, and
        categories are preserved """
        import_competency_set(load_bundled_set('bc-math-8'))
        original = list(Competency.objects.values('source_id', 'name', 'category', 'description'))

        exported = json.dumps(export_competency_set(name='Round trip'))
        Competency.objects.all().delete()  # simulate the second, empty deck

        created, updated = import_competency_set(parse_json_set(exported))
        self.assertEqual(updated, 0)
        self.assertEqual(created, len(original))
        self.assertEqual(
            list(Competency.objects.values('source_id', 'name', 'category', 'description')),
            original,
        )

    def test_export_import_round_trip__csv(self):
        """ Export to CSV then import restores the same competencies """
        import_competency_set(load_bundled_set('bc-core-competencies'))
        original = list(Competency.objects.values('source_id', 'name', 'category', 'description'))

        exported = export_csv()
        Competency.objects.all().delete()

        created, updated = import_competency_set(parse_csv_set(exported))
        self.assertEqual(updated, 0)
        self.assertEqual(created, len(original))
        self.assertEqual(
            list(Competency.objects.values('source_id', 'name', 'category', 'description')),
            original,
        )
