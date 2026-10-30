import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError


from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from competencies.import_export import load_bundled_set
from competencies.models import Competency


class ImportCompetenciesCommandTest(ByteDeckTenantTestCase):
    """ Tests for the import_competencies management command. """

    def test_import_competencies__bundled_set_is_idempotent(self):
        """ The --set option imports a bundled set, and a re-run is idempotent """
        out = StringIO()
        call_command('import_competencies', '--set', 'bc-core-competencies', stdout=out)

        expected = len(load_bundled_set('bc-core-competencies')['entries'])
        self.assertEqual(Competency.objects.count(), expected)
        self.assertIn(f'{expected} created', out.getvalue())

        # idempotent on re-run
        out = StringIO()
        call_command('import_competencies', '--set', 'bc-core-competencies', stdout=out)
        self.assertEqual(Competency.objects.count(), expected)
        self.assertIn('0 created', out.getvalue())

    def test_import_competencies__json_file(self):
        """ The --file option imports a .json competency-set file """
        content = {
            'format': 'bytedeck-competency-set',
            'version': 1,
            'name': 'From file',
            'entries': [{'source_id': 'x:1', 'name': 'From a file'}],
        }
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'set.json'
            path.write_text(json.dumps(content), encoding='utf-8')
            call_command('import_competencies', '--file', str(path), stdout=StringIO())

        self.assertTrue(Competency.objects.filter(name='From a file').exists())

    def test_import_competencies__csv_file(self):
        """ The --file option imports a .csv competency-set file """
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'set.csv'
            path.write_text("name,category\nCSV file competency,Strand\n", encoding='utf-8')
            call_command('import_competencies', '--file', str(path), stdout=StringIO())

        self.assertTrue(Competency.objects.filter(name='CSV file competency').exists())

    def test_import_competencies__unknown_bundled_set_errors(self):
        """ An unknown --set key fails with a CommandError """
        with self.assertRaises(CommandError):
            call_command('import_competencies', '--set', 'no-such-set', stdout=StringIO())

    def test_import_competencies__missing_file_errors(self):
        """ A nonexistent --file path fails with a CommandError """
        with self.assertRaises(CommandError):
            call_command('import_competencies', '--file', '/no/such/file.json', stdout=StringIO())

    def test_import_competencies__malformed_file_errors(self):
        """ A file that fails parsing/validation fails with a CommandError """
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'broken.json'
            path.write_text('{not json', encoding='utf-8')
            with self.assertRaises(CommandError):
                call_command('import_competencies', '--file', str(path), stdout=StringIO())

    def test_import_competencies__list_prints_bundled_sets(self):
        """ The --list option prints the available bundled set keys """
        out = StringIO()
        call_command('import_competencies', '--list', stdout=out)
        self.assertIn('bc-core-competencies', out.getvalue())


class ExportCompetenciesCommandTest(ByteDeckTenantTestCase):
    """ Tests for the export_competencies management command. """

    def setUp(self):
        """ Imports a bundled set so there is something to export. """
        call_command('import_competencies', '--set', 'bc-math-8', stdout=StringIO())

    def test_export_competencies__json_to_stdout(self):
        """ The default invocation writes the deck's competencies as JSON to stdout """
        out = StringIO()
        call_command('export_competencies', stdout=out)
        data = json.loads(out.getvalue())

        self.assertEqual(data['format'], 'bytedeck-competency-set')
        self.assertEqual(len(data['entries']), Competency.objects.count())

    def test_export_competencies__csv_to_file(self):
        """ --format csv --output writes a CSV competency set to the given file """
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'out.csv'
            call_command('export_competencies', '--format', 'csv', '--output', str(path), stdout=StringIO())
            content = path.read_text(encoding='utf-8')

        self.assertTrue(content.startswith('course,category,name,description,source_id'))
        self.assertIn('Estimate reasonably', content)

    def test_export_competencies__unwritable_output_path(self):
        """ An --output path that can't be written (its directory doesn't exist) is a CommandError, not a traceback """
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'no-such-dir' / 'out.json'
            with self.assertRaises(CommandError):
                call_command('export_competencies', '--output', str(path), stdout=StringIO())
