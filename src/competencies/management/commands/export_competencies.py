import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from competencies.import_export import export_competency_set, export_csv


class Command(BaseCommand):
    help = (
        "Export a tenant's active competencies as a portable competency set. "
        'Run per-tenant, e.g.: ./manage.py tenant_command export_competencies --schema=myschema > competencies.json'
    )

    def add_arguments(self, parser):
        """ Adds the command's options to the argument parser: --format chooses the
        output serialization (json, the default, or csv) and --output redirects the
        export to a file instead of stdout.
        """
        parser.add_argument('--format', choices=['json', 'csv'], default='json', help='Output format (default: json)')
        parser.add_argument('--output', help='Write to this file instead of stdout')

    def handle(self, *args, **options):
        """ Serializes the current tenant's active competencies in the requested
        format and writes the result to the --output file (with a success note to
        stdout) or directly to stdout. Returns None.

        Raises:
            CommandError: if the output file can't be written.
        """
        if options['format'] == 'csv':
            content = export_csv()
        else:
            content = json.dumps(export_competency_set(), indent=4) + '\n'

        if options['output']:
            try:
                Path(options['output']).write_text(content, encoding='utf-8')
            except OSError as e:
                raise CommandError(str(e)) from e
            self.stdout.write(self.style.SUCCESS(f"Exported to {options['output']}"))
        else:
            self.stdout.write(content)
