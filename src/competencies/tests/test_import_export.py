import json
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from competencies.import_export import (
    export_competency_set,
    export_csv,
    get_bundled_set_keys,
    import_competency_set,
    load_bundled_set,
    parse_csv_set,
    parse_json_set,
    parse_uploaded_file,
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


class ParseAndValidateTest(ByteDeckTenantTestCase):
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
            {'course': '', 'source_id': 'x:1', 'name': 'Think', 'description': 'desc', 'category': 'Thinking'}
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

    def test_validate_competency_set__boolean_version(self):
        """ A version of true is rejected, although Python treats True as the int 1 """
        with self.assertRaises(ValidationError):
            validate_competency_set(make_set([{'name': 'x'}], version=True))

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
            'course': '', 'name': 'Think critically', 'category': 'Thinking', 'description': 'A description', 'source_id': 'x:1',
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

    def test_parse_csv_set__not_utf8(self):
        """ CSV bytes that aren't UTF-8 text are rejected with a ValidationError """
        with self.assertRaises(ValidationError):
            parse_csv_set(b'name\n\xff\xfe broken\n')

    def test_parse_csv_set__blank_trailing_cells_are_ignored(self):
        """ Empty cells past the header (a trailing comma, as spreadsheets often export) are
        not "more cells than the header": the row still imports """
        competency_set = parse_csv_set("name,category\nThink,Thinking,\n")
        self.assertEqual(competency_set['entries'][0]['category'], 'Thinking')

    def test_parse_csv_set__value_under_a_blank_header(self):
        """ A value in a column with a blank header is rejected rather than silently dropped,
        wherever that column is and however many blank-header columns there are """
        for raw in ["name,category,\nThink,Thinking,x\n", "name,,category,\nThink,x,Thinking,\n"]:
            with self.subTest(raw=raw), self.assertRaisesMessage(ValidationError, "Line 2 has a value in a column with no header."):
                parse_csv_set(raw)

    def test_parse_csv_set__blank_cells_under_blank_headers_are_ignored(self):
        """ Blank cells under blank headers (a trailing comma on every line, or an empty spacer
        column) are fine: the rows still import """
        for raw in ["name,category,\nThink,Thinking,\n", "name,,category\nThink,,Thinking\n"]:
            with self.subTest(raw=raw):
                self.assertEqual(parse_csv_set(raw)['entries'], [
                    {'course': '', 'name': 'Think', 'category': 'Thinking', 'description': '', 'source_id': ''},
                ])

    def test_parse_uploaded_file__unsupported_extension(self):
        """ An upload that is neither .json nor .csv is rejected with a ValidationError """
        with self.assertRaises(ValidationError):
            parse_uploaded_file(SimpleUploadedFile('set.txt', b'name\nThink\n'))

    def test_validate_competency_set__not_an_object(self):
        """ A set that isn't a JSON object (e.g. a bare list) is rejected """
        with self.assertRaises(ValidationError):
            validate_competency_set([{'name': 'Think'}])

    def test_validate_competency_set__entry_not_an_object(self):
        """ An entry that isn't a JSON object (e.g. a bare string) is rejected """
        with self.assertRaises(ValidationError):
            validate_competency_set(make_set(['Think']))

    def test_parse_csv_set__header_names_ignore_case_and_whitespace(self):
        """ Headers like "Name, Category" (a common spreadsheet layout) are read the same as
        "name,category": the rows' values are found under the normalized column names """
        competency_set = parse_csv_set("Name, Category\nThink,Thinking\n")
        self.assertEqual(competency_set['entries'][0]['name'], 'Think')
        self.assertEqual(competency_set['entries'][0]['category'], 'Thinking')

    def test_parse_csv_set__duplicate_columns(self):
        """ Two headers naming the same column, in any case, are rejected instead of one
        column's values being silently dropped """
        with self.assertRaisesMessage(ValidationError, "Duplicate CSV column(s): name"):
            parse_csv_set("name,Name\nThink,Reflect\n")

    def test_parse_csv_set__row_with_more_cells_than_the_header(self):
        """ A row with surplus cells is rejected with a ValidationError rather than crashing """
        with self.assertRaises(ValidationError):
            parse_csv_set("name,category\nThink,Thinking,extra\n")

    def test_validate_competency_set__rejects_non_string_entry_fields(self):
        """ An entry field holding a list, object, or number is rejected instead of being stored
        as its Python repr (e.g. a name of ["a"] becoming the text "['a']") """
        for field in ['course', 'name', 'description', 'category', 'source_id']:
            for value in [['a'], {'a': 1}, 42]:
                entry = {'name': 'Think', field: value}
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                    validate_competency_set(make_set([entry]))

    def test_validate_competency_set__rejects_non_string_metadata(self):
        """ Set metadata such as the set name must be text too, and the error names it as the
        set's field rather than an entry's """
        with self.assertRaisesMessage(ValidationError, "The set's name must be text."):
            validate_competency_set(make_set([{'name': 'Think'}], name=['a']))

    def test_validate_competency_set__malformed_source_url(self):
        """ A source_url that urlsplit can't parse at all is a validation error, not a crash """
        with self.assertRaisesMessage(ValidationError, "source_url must be an http or https URL."):
            validate_competency_set(make_set([{'name': 'Think'}], source_url='http://[::1'))

    def test_validate_competency_set__source_url_must_be_http_or_https(self):
        """ source_url is rendered as a link in the import preview, so only http(s) URLs (or none)
        are accepted: a javascript: URL would run script for the staff user who clicks it """
        for url in ['javascript:alert(1)', 'JavaScript:alert(1)', 'data:text/html,hi', 'ftp://example.com/set']:
            with self.subTest(url=url), self.assertRaises(ValidationError):
                validate_competency_set(make_set([{'name': 'Think'}], source_url=url))

        for url in ['', 'http://example.com/set', 'https://curriculum.gov.bc.ca/competencies']:
            with self.subTest(url=url):
                self.assertEqual(validate_competency_set(make_set([{'name': 'Think'}], source_url=url))['source_url'], url)

    def test_validate_competency_set__rejects_overlong_category_and_source_id(self):
        """ Every length-limited field is checked up front, so an overlong value is a validation
        error before anything is imported, not a failure part way through the import """
        for field in ['course', 'category', 'source_id']:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate_competency_set(make_set([{'name': 'Think', field: 'x' * 256}]))

    def test_validate_competency_set__entries_take_the_sets_course(self):
        """ An entry without a course takes the set's; one with its own keeps it """
        competency_set = validate_competency_set(make_set([{'name': 'Think'}, {'name': 'Share', 'course': 'Other'}], course='Core'))

        self.assertEqual(competency_set['course'], 'Core')
        self.assertEqual([entry['course'] for entry in competency_set['entries']], ['Core', 'Other'])

    def test_validate_competency_set__rejects_a_non_text_set_course(self):
        """ The set's course must be text too """
        with self.assertRaisesMessage(ValidationError, "The set's course must be text."):
            validate_competency_set(make_set([{'name': 'Think'}], course=['Core']))

    def test_parse_csv_set__reads_the_course_column(self):
        """ A CSV's course column gives each row its course """
        competency_set = parse_csv_set("course,category,name\nADST 9,Defining,Choose a design opportunity\n")
        self.assertEqual(competency_set['entries'][0]['course'], 'ADST 9')


class BundledSetsTest(ByteDeckTenantTestCase):
    """ Tests for the curriculum datasets bundled in the app's data/ directory. """

    def test_get_bundled_set_keys__every_set_exists_and_is_valid(self):
        """ Every dataset bundled in data/ parses and validates """
        keys = get_bundled_set_keys()
        self.assertIn('bc-core-competencies', keys)
        self.assertIn('bc-adst-8', keys)
        self.assertIn('bc-math-8', keys)

        for key in keys:
            competency_set = load_bundled_set(key)  # raises if invalid
            self.assertTrue(competency_set['name'])
            self.assertTrue(competency_set['entries'])
            # bundled curriculum entries all carry a stable source_id for re-import de-dup, and the
            # set's course, so pickers can tell competencies from different sets apart
            self.assertTrue(competency_set['course'], f"{key} names no course")
            for entry in competency_set['entries']:
                self.assertTrue(entry['source_id'], f"{key}: entry {entry['name']} is missing a source_id")
                self.assertEqual(entry['course'], competency_set['course'])

    def test_bundled_sets__courses_and_source_ids_are_unique_across_sets(self):
        """ No two bundled sets share a course or a source_id, so importing several never merges
        one course's competency into another's """
        courses, source_ids = [], []
        for key in get_bundled_set_keys():
            competency_set = load_bundled_set(key)
            courses.append(competency_set['course'])
            source_ids.extend(entry['source_id'] for entry in competency_set['entries'])
        self.assertEqual(len(courses), len(set(courses)))
        self.assertEqual(len(source_ids), len(set(source_ids)))

    def test_load_bundled_set__adst_8_matches_the_official_curriculum(self):
        """ The ADST 8 set carries grade 8's own Testing competencies, as published at its
        source_url, not the grade 9 wording an earlier version of the set had """
        competency_set = load_bundled_set('bc-adst-8')
        testing = [entry['name'] for entry in competency_set['entries'] if entry['category'] == 'Testing']

        self.assertEqual(testing, [
            "Test the first version of the product or the prototype",
            "Gather peer and/or user and/or expert feedback and inspiration",
            "Make changes, troubleshoot, and test again",
        ])

    def test_load_bundled_set__unknown_key(self):
        """ Asking for a bundled set that doesn't exist raises a ValidationError """
        with self.assertRaises(ValidationError):
            load_bundled_set('no-such-set')

    def test_load_bundled_set__rejects_path_traversal(self):
        """ A path-traversal key can't escape the bundled data directory """
        with self.assertRaises(ValidationError):
            load_bundled_set('../secrets')


class ImportCompetencySetTest(ByteDeckTenantTestCase):
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

    def test_import__course_is_set_and_updated_but_never_cleared(self):
        """ Importing sets a competency's course and a re-import changes it, but a re-import that
        gives no course (a CSV without the column) leaves the course it has """
        import_competency_set(make_valid_set([{'source_id': 'x:1', 'name': 'Think'}], course='Old course'))
        self.assertEqual(Competency.objects.get().course, 'Old course')

        import_competency_set(make_valid_set([{'source_id': 'x:1', 'name': 'Think'}], course='New course'))
        self.assertEqual(Competency.objects.get().course, 'New course')

        import_competency_set(parse_csv_set("name,source_id\nThink,x:1\n"))
        self.assertEqual(Competency.objects.get().course, 'New course')

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

    def test_preview_entry_statuses__marks_update_or_create(self):
        """ The preview marks entries as update or create depending on whether a match exists """
        baker.make(Competency, name='Existing', source_id='x:1')
        entries = preview_entry_statuses(make_valid_set([
            {'source_id': 'x:1', 'name': 'Existing'},
            {'source_id': 'x:2', 'name': 'Brand new'},
        ]))
        self.assertEqual([e['status'] for e in entries], ['update', 'create'])

    def test_preview_entry_statuses__unsourced_competency_is_claimed_once(self):
        """ The preview agrees with the import: only the first of two sourced entries sharing a
        hand-typed competency's name adopts it, and the second would be created """
        baker.make(Competency, name='Estimate reasonably', source_id=None)
        entries = preview_entry_statuses(make_valid_set([
            {'source_id': 'bc:math:7:reasoning-3', 'name': 'Estimate reasonably'},
            {'source_id': 'bc:math:8:reasoning-3', 'name': 'Estimate reasonably'},
        ]))
        self.assertEqual([e['status'] for e in entries], ['update', 'create'])

    def test_import__unsourced_competency_is_claimed_once(self):
        """ Two sourced entries with a hand-typed competency's name: the first adopts it and the
        second is created, rather than the second overwriting the first's source_id and content """
        hand_typed = baker.make(Competency, name='Estimate reasonably', source_id=None)

        created, updated = import_competency_set(make_valid_set([
            {'source_id': 'bc:math:7:reasoning-3', 'name': 'Estimate reasonably', 'category': 'Grade 7'},
            {'source_id': 'bc:math:8:reasoning-3', 'name': 'Estimate reasonably', 'category': 'Grade 8'},
        ]))

        self.assertEqual((created, updated), (1, 1))
        hand_typed.refresh_from_db()
        self.assertEqual((hand_typed.source_id, hand_typed.category), ('bc:math:7:reasoning-3', 'Grade 7'))
        self.assertEqual(Competency.objects.get(source_id='bc:math:8:reasoning-3').category, 'Grade 8')

    def test_import__failure_part_way_saves_nothing(self):
        """ The import is all or nothing: if saving one entry fails, the entries before it are
        rolled back too, rather than leaving a partly imported set """
        competency_set = make_valid_set([{'source_id': 'x:1', 'name': 'a'}, {'source_id': 'x:2', 'name': 'b'}])

        with patch.object(Competency, 'full_clean', side_effect=[None, ValidationError('boom')]):
            with self.assertRaises(ValidationError):
                import_competency_set(competency_set)

        self.assertFalse(Competency.objects.exists())


class ExportRoundTripTest(ByteDeckTenantTestCase):
    """ Tests for the exporters and full export-import round trips. """

    def test_export_competency_set__given_queryset(self):
        """ When a queryset is passed, exactly those competencies are exported (inactive ones included) """
        retired = baker.make(Competency, name='Retired one', active=False)
        baker.make(Competency, name='Active one', active=True)

        competency_set = export_competency_set(Competency.objects.filter(pk=retired.pk))
        self.assertEqual([e['name'] for e in competency_set['entries']], ['Retired one'])

    def test_export__active_competencies_only(self):
        """ The default export includes active competencies and skips deactivated ones """
        baker.make(Competency, name='Active one', active=True)
        baker.make(Competency, name='Retired one', active=False)

        competency_set = export_competency_set()
        names = [e['name'] for e in competency_set['entries']]
        self.assertIn('Active one', names)
        self.assertNotIn('Retired one', names)

    def test_export_import_round_trip__json(self):
        """ Export from one deck, import into another: courses, source_ids, names, and
        categories are preserved """
        import_competency_set(load_bundled_set('bc-math-8'))
        original = list(Competency.objects.values('course', 'source_id', 'name', 'category', 'description'))

        exported = json.dumps(export_competency_set(name='Round trip'))
        Competency.objects.all().delete()  # simulate the second, empty deck

        created, updated = import_competency_set(parse_json_set(exported))
        self.assertEqual(updated, 0)
        self.assertEqual(created, len(original))
        self.assertEqual(
            list(Competency.objects.values('course', 'source_id', 'name', 'category', 'description')),
            original,
        )

    def test_export_import_round_trip__csv(self):
        """ Export to CSV then import restores the same competencies """
        import_competency_set(load_bundled_set('bc-core-competencies'))
        original = list(Competency.objects.values('course', 'source_id', 'name', 'category', 'description'))

        exported = export_csv()
        Competency.objects.all().delete()

        created, updated = import_competency_set(parse_csv_set(exported))
        self.assertEqual(updated, 0)
        self.assertEqual(created, len(original))
        self.assertEqual(
            list(Competency.objects.values('course', 'source_id', 'name', 'category', 'description')),
            original,
        )
