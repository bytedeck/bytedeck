from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from competencies.import_export import (
    get_bundled_set_keys,
    import_competency_set,
    load_bundled_set,
    parse_csv_set,
    parse_json_set,
)


class Command(BaseCommand):
    help = (
        'Import a competency set (bundled, JSON, or CSV) into a tenant. '
        'Run per-tenant, e.g.: ./manage.py tenant_command import_competencies --set bc-core-competencies --schema=myschema'
    )

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument('--set', help='Key of a bundled competency set (see --list)')
        group.add_argument('--file', help='Path to a .json or .csv competency set file')
        group.add_argument('--list', action='store_true', help='List the available bundled competency sets')

    def handle(self, *args, **options):
        if options['list']:
            for key in get_bundled_set_keys():
                self.stdout.write(f"{key}: {load_bundled_set(key)['name']}")
            return

        try:
            if options['set']:
                competency_set = load_bundled_set(options['set'])
            else:
                path = Path(options['file'])
                if not path.is_file():
                    raise CommandError(f"File not found: {path}")
                if path.suffix.lower() == '.csv':
                    competency_set = parse_csv_set(path.read_bytes(), name=path.stem)
                else:
                    competency_set = parse_json_set(path.read_bytes())
        except ValidationError as e:
            raise CommandError('; '.join(e.messages))

        created, updated = import_competency_set(competency_set)
        self.stdout.write(self.style.SUCCESS(
            f"Imported \"{competency_set['name'] or 'competency set'}\": {created} created, {updated} updated."
        ))
