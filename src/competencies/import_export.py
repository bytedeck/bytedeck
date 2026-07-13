"""Portable competency-set format: parsing, validation, import, and export.

A "competency set" is a versioned JSON document describing a list of competencies
that can be moved between decks (or curated in this repo as bundled curriculum data):

    {
        "format": "bytedeck-competency-set",
        "version": 1,
        "name": "BC Grade 8 Mathematics Curricular Competencies",
        "jurisdiction": "BC",
        "subject": "Mathematics",
        "grade": "8",
        "source_url": "https://curriculum.gov.bc.ca/curriculum/mathematics/8/core",
        "entries": [
            {
                "source_id": "bc:math:8:reasoning-1",
                "name": "Use logic and patterns to solve puzzles and play games",
                "description": "",
                "category": "Reasoning and analyzing"
            }
        ]
    }

Set metadata other than ``entries`` is informational. Each entry requires a ``name``;
``source_id``, ``description``, and ``category`` are optional. ``source_id`` is a stable
identifier into the source taxonomy (convention for BC: ``bc:{subject}:{grade}:{slug}``)
and is the key used to de-duplicate re-imports and, later, to match competencies
across decks in the Library.

CSV is supported as a lower-friction alternative for teacher-authored sets. The
required header row is ``name,category,description,source_id`` (column order doesn't
matter; only ``name`` is required to have a value). Exports produce the same layout,
so export -> import round-trips work in both formats.

Bundled curriculum datasets live in this app's ``data/`` directory, one JSON file
per set, keyed by filename stem.
"""

import csv
import io
import json
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import models

from .models import Competency

FORMAT_NAME = 'bytedeck-competency-set'
FORMAT_VERSION = 1

CSV_FIELDS = ['name', 'category', 'description', 'source_id']

DATA_DIR = Path(__file__).resolve().parent / 'data'


def validate_competency_set(data):
    """ Validate a parsed competency-set dict, returning it in normalized form
    (whitespace stripped, missing optional keys filled with defaults).

    Raises ValidationError with a human-readable message on any problem.
    """
    if not isinstance(data, dict):
        raise ValidationError("A competency set must be a JSON object.")

    if data.get('format') != FORMAT_NAME:
        raise ValidationError(f"Not a competency set: expected \"format\": \"{FORMAT_NAME}\".")

    version = data.get('version')
    if not isinstance(version, int) or version < 1 or version > FORMAT_VERSION:
        raise ValidationError(f"Unsupported competency set version: {version!r} (this deck supports up to {FORMAT_VERSION}).")

    entries = data.get('entries')
    if not isinstance(entries, list) or not entries:
        raise ValidationError("The competency set has no entries.")

    normalized_entries = []
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValidationError(f"Entry {i} is not an object.")

        name = str(entry.get('name') or '').strip()
        if not name:
            raise ValidationError(f"Entry {i} is missing a name.")

        max_length = Competency._meta.get_field('name').max_length
        if len(name) > max_length:
            raise ValidationError(f"Entry {i}: name is longer than {max_length} characters.")

        normalized_entries.append({
            'name': name,
            'description': str(entry.get('description') or '').strip(),
            'category': str(entry.get('category') or '').strip(),
            'source_id': str(entry.get('source_id') or '').strip(),
        })

    source_ids = [e['source_id'] for e in normalized_entries if e['source_id']]
    if len(source_ids) != len(set(source_ids)):
        raise ValidationError("The competency set contains duplicate source_ids.")

    return {
        'format': FORMAT_NAME,
        'version': version,
        'name': str(data.get('name') or '').strip(),
        'jurisdiction': str(data.get('jurisdiction') or '').strip(),
        'subject': str(data.get('subject') or '').strip(),
        'grade': str(data.get('grade') or '').strip(),
        'source_url': str(data.get('source_url') or '').strip(),
        'entries': normalized_entries,
    }


def parse_json_set(raw):
    """ Parse and validate a JSON competency set from a str or bytes.
    Raises ValidationError on malformed input.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode('utf-8')
        except UnicodeDecodeError:
            raise ValidationError("The file is not valid UTF-8 text.")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValidationError(f"The file is not valid JSON: {e}")
    return validate_competency_set(data)


def parse_csv_set(raw, name=''):
    """ Parse and validate a CSV competency set from a str or bytes.

    The header row must include a `name` column; `category`, `description` and
    `source_id` columns are optional. Raises ValidationError on malformed input.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode('utf-8-sig')  # tolerate an Excel BOM
        except UnicodeDecodeError:
            raise ValidationError("The file is not valid UTF-8 text.")

    reader = csv.DictReader(io.StringIO(raw))
    header = [h.strip().lower() for h in reader.fieldnames or []]
    if 'name' not in header:
        raise ValidationError(
            f"The CSV file must have a header row including a \"name\" column. Expected columns: {', '.join(CSV_FIELDS)}."
        )
    unknown = [h for h in header if h and h not in CSV_FIELDS]
    if unknown:
        raise ValidationError(
            f"Unknown CSV column(s): {', '.join(unknown)}. Expected columns: {', '.join(CSV_FIELDS)}."
        )

    entries = [
        {field: (row.get(field) or '').strip() for field in CSV_FIELDS}
        for row in reader
        # ignore fully blank lines
        if any((value or '').strip() for value in row.values())
    ]

    return validate_competency_set({
        'format': FORMAT_NAME,
        'version': FORMAT_VERSION,
        'name': name,
        'entries': entries,
    })


def parse_uploaded_file(uploaded_file):
    """ Parse an uploaded competency-set file, dispatching on its extension
    (.json or .csv). Raises ValidationError for anything else or on parse failure.
    """
    filename = (uploaded_file.name or '').lower()
    raw = uploaded_file.read()
    if filename.endswith('.json'):
        return parse_json_set(raw)
    elif filename.endswith('.csv'):
        return parse_csv_set(raw, name=Path(filename).stem)
    raise ValidationError("Unsupported file type. Upload a .json or .csv competency set.")


def get_bundled_set_keys():
    """ Returns the sorted list of bundled set keys (data/ filename stems). """
    return sorted(path.stem for path in DATA_DIR.glob('*.json'))


def load_bundled_set(key):
    """ Load and validate a bundled competency set by key.
    Raises ValidationError if the key doesn't exist (or the dataset is broken).
    """
    if key not in get_bundled_set_keys():  # also excludes path tricks like '../'
        raise ValidationError(f"Unknown bundled competency set: {key}")
    return parse_json_set((DATA_DIR / f'{key}.json').read_text(encoding='utf-8'))


def preview_entry_statuses(competency_set):
    """ Returns the set's entries, each annotated with the action an import would
    take: 'update' (a matching competency exists) or 'create'.
    """
    entries = []
    for entry in competency_set['entries']:
        entry = dict(entry)
        entry['status'] = 'update' if _find_existing(entry) else 'create'
        entries.append(entry)
    return entries


def _find_existing(entry):
    """ Find the existing Competency an entry corresponds to, or None.

    An entry with a source_id matches on source_id first, then falls back to a
    case-insensitive name match against competencies *without* a source_id (so a
    curriculum import can adopt hand-typed competencies instead of duplicating
    them — but never hijacks a competency that belongs to a different taxonomy
    entry with the same name, e.g. the same wording in two grades' sets).

    An entry without a source_id (e.g. from a teacher-authored CSV) matches on
    name alone, keeping re-imports idempotent.
    """
    no_source_id = models.Q(source_id__isnull=True) | models.Q(source_id='')
    if entry['source_id']:
        return (
            Competency.objects.filter(source_id=entry['source_id']).first()
            or Competency.objects.filter(no_source_id, name__iexact=entry['name']).first()
        )
    return Competency.objects.filter(name__iexact=entry['name']).first()


def import_competency_set(competency_set, selected_indexes=None):
    """ Import a validated competency set into the current deck.

    Entries matching an existing competency (see _find_existing) are updated in
    place — never duplicated — so re-importing a set is idempotent. The `active`
    flag of existing competencies is left alone (deactivation is a deck-level
    decision that a re-import shouldn't quietly reverse).

    Args:
        competency_set (dict): a set as returned by the parse/validate functions.
        selected_indexes (list[int], optional): indexes into entries to import;
            all entries when None.

    Returns:
        tuple[int, int]: (created_count, updated_count)
    """
    entries = competency_set['entries']
    if selected_indexes is not None:
        entries = [entries[i] for i in selected_indexes if 0 <= i < len(entries)]

    created = updated = 0
    for entry in entries:
        existing = _find_existing(entry)
        if existing:
            existing.name = entry['name']
            existing.description = entry['description']
            existing.category = entry['category']
            if entry['source_id']:
                existing.source_id = entry['source_id']
            existing.save()
            updated += 1
        else:
            Competency.objects.create(
                name=entry['name'],
                description=entry['description'],
                category=entry['category'],
                source_id=entry['source_id'] or None,
            )
            created += 1
    return created, updated


def export_competency_set(queryset=None, name=''):
    """ Serialize competencies to a competency-set dict (the deck's active
    competencies by default) suitable for json.dumps and re-import elsewhere.
    """
    if queryset is None:
        queryset = Competency.objects.active()
    return {
        'format': FORMAT_NAME,
        'version': FORMAT_VERSION,
        'name': name,
        'jurisdiction': '',
        'subject': '',
        'grade': '',
        'source_url': '',
        'entries': [
            {
                'source_id': competency.source_id or '',
                'name': competency.name,
                'description': competency.description,
                'category': competency.category,
            }
            for competency in queryset
        ],
    }


def export_csv(queryset=None):
    """ Serialize competencies to CSV text (same columns the CSV importer accepts). """
    competency_set = export_competency_set(queryset)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for entry in competency_set['entries']:
        writer.writerow({field: entry[field] for field in CSV_FIELDS})
    return out.getvalue()
