import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError

from django_tenants.test.cases import TenantTestCase

from competencies.import_export import load_bundled_set
from competencies.models import Competency


class ImportCompetenciesCommandTest(TenantTestCase):

    def test_import_bundled_set(self):
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

    def test_import_json_file(self):
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

    def test_import_csv_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'set.csv'
            path.write_text("name,category\nCSV file competency,Strand\n", encoding='utf-8')
            call_command('import_competencies', '--file', str(path), stdout=StringIO())

        self.assertTrue(Competency.objects.filter(name='CSV file competency').exists())

    def test_import_unknown_bundled_set(self):
        with self.assertRaises(CommandError):
            call_command('import_competencies', '--set', 'no-such-set', stdout=StringIO())

    def test_import_missing_file(self):
        with self.assertRaises(CommandError):
            call_command('import_competencies', '--file', '/no/such/file.json', stdout=StringIO())

    def test_import_malformed_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'broken.json'
            path.write_text('{not json', encoding='utf-8')
            with self.assertRaises(CommandError):
                call_command('import_competencies', '--file', str(path), stdout=StringIO())

    def test_list_bundled_sets(self):
        out = StringIO()
        call_command('import_competencies', '--list', stdout=out)
        self.assertIn('bc-core-competencies', out.getvalue())


class ExportCompetenciesCommandTest(TenantTestCase):

    def setUp(self):
        call_command('import_competencies', '--set', 'bc-math-8', stdout=StringIO())

    def test_export_json_to_stdout(self):
        out = StringIO()
        call_command('export_competencies', stdout=out)
        data = json.loads(out.getvalue())

        self.assertEqual(data['format'], 'bytedeck-competency-set')
        self.assertEqual(len(data['entries']), Competency.objects.count())

    def test_export_csv_to_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'out.csv'
            call_command('export_competencies', '--format', 'csv', '--output', str(path), stdout=StringIO())
            content = path.read_text(encoding='utf-8')

        self.assertTrue(content.startswith('name,category,description,source_id'))
        self.assertIn('Estimate reasonably', content)
