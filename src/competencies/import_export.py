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
``source_id``, ``description``, and ``category`` are optional. Every field is text (a JSON
string), and ``source_url``, when given, must be an http(s) URL. ``source_id`` is a stable
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
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.functions import Lower

from .models import Competency

FORMAT_NAME = 'bytedeck-competency-set'
FORMAT_VERSION = 1

CSV_FIELDS = ['name', 'category', 'description', 'source_id']

# The source_url is rendered as a link in the import preview, so anything that a browser would
# run rather than navigate to (javascript:, data:, ...) is refused.
SOURCE_URL_SCHEMES = ('http', 'https')

# The Competency fields with a max_length, checked before anything is saved.
LENGTH_LIMITED_FIELDS = ('name', 'category', 'source_id')

DATA_DIR = Path(__file__).resolve().parent / 'data'


def _text(value, label):
    """ Normalize one text field of a competency set.

    Args:
        value: the raw value from the parsed file.
        label (str): how to name the field in an error message.

    Returns:
        str: the value with surrounding whitespace stripped, or '' when it is missing or None.

    Raises:
        ValidationError: if the value is anything other than a string (a list, object, or
            number would otherwise be stored as its Python repr).
    """
    if value is None:
        return ''
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text.")
    return value.strip()


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
    # bool is a subclass of int, so a version of true would otherwise pass as 1
    if isinstance(version, bool) or not isinstance(version, int) or version < 1 or version > FORMAT_VERSION:
        raise ValidationError(f"Unsupported competency set version: {version!r} (this deck supports up to {FORMAT_VERSION}).")

    entries = data.get('entries')
    if not isinstance(entries, list) or not entries:
        raise ValidationError("The competency set has no entries.")

    normalized_entries = []
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ValidationError(f"Entry {i} is not an object.")

        normalized = {field: _text(entry.get(field), f"Entry {i}: {field}") for field in CSV_FIELDS}
        if not normalized['name']:
            raise ValidationError(f"Entry {i} is missing a name.")

        for field in LENGTH_LIMITED_FIELDS:
            max_length = Competency._meta.get_field(field).max_length
            if len(normalized[field]) > max_length:
                raise ValidationError(f"Entry {i}: {field} is longer than {max_length} characters.")

        normalized_entries.append(normalized)

    source_ids = [e['source_id'] for e in normalized_entries if e['source_id']]
    if len(source_ids) != len(set(source_ids)):
        raise ValidationError("The competency set contains duplicate source_ids.")

    metadata = {key: _text(data.get(key), f"The set's {key}") for key in ('name', 'jurisdiction', 'subject', 'grade', 'source_url')}
    if metadata['source_url']:
        try:
            scheme = urlsplit(metadata['source_url']).scheme
        except ValueError:  # urlsplit rejects some malformed URLs outright, e.g. "http://[::1"
            scheme = None
        if scheme not in SOURCE_URL_SCHEMES:
            raise ValidationError("source_url must be an http or https URL.")

    return {
        'format': FORMAT_NAME,
        'version': version,
        **metadata,
        'entries': normalized_entries,
    }


def parse_json_set(raw):
    """ Parse and validate a JSON competency set from a str or bytes.
    Raises ValidationError on malformed input.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode('utf-8')
        except UnicodeDecodeError as e:
            raise ValidationError("The file is not valid UTF-8 text.") from e
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValidationError(f"The file is not valid JSON: {e}") from e
    return validate_competency_set(data)


def parse_csv_set(raw, name=''):
    """ Parse and validate a CSV competency set from a str or bytes.

    The header row must include a `name` column; `category`, `description` and
    `source_id` columns are optional. Raises ValidationError on malformed input.
    """
    if isinstance(raw, bytes):
        try:
            raw = raw.decode('utf-8-sig')  # tolerate an Excel BOM
        except UnicodeDecodeError as e:
            raise ValidationError("The file is not valid UTF-8 text.") from e

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
    # two headers that normalize to the same name ("Name" and "name") would leave one column's
    # values silently ignored
    duplicates = sorted({h for h in header if h and header.count(h) > 1})
    if duplicates:
        raise ValidationError(f"Duplicate CSV column(s): {', '.join(duplicates)}. Each column can appear only once.")
    # read the rows under the normalized names, so "Name" or " name" columns are found as "name".
    # Each blank header gets a key of its own (DictReader would put them all under '', where
    # they overwrite each other), so every cell under one can be checked.
    reader.fieldnames = [h or f'__unnamed_{index}' for index, h in enumerate(header)]
    unnamed = [key for key in reader.fieldnames if key not in header]

    entries = []
    for row in reader:
        # DictReader collects cells beyond the header under the key None. Blank ones there, or
        # under a blank header, are just trailing commas, but a value in either has no column to go in.
        surplus = row.pop(None, None) or []
        if any(cell.strip() for cell in surplus):
            raise ValidationError(f"Line {reader.line_num} has more cells than the header row.")
        if any((row.pop(key) or '').strip() for key in unnamed):
            raise ValidationError(f"Line {reader.line_num} has a value in a column with no header.")
        if not any((value or '').strip() for value in row.values()):
            continue  # ignore fully blank lines
        entries.append({field: (row.get(field) or '').strip() for field in CSV_FIELDS})

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
    lookup = _build_existing_lookup(competency_set['entries'])
    entries = []
    for entry, existing in _match_entries(competency_set['entries'], lookup):
        entry = dict(entry)
        entry['status'] = 'update' if existing else 'create'
        entries.append(entry)
    return entries


def _build_existing_lookup(entries):
    """ Prefetch every existing Competency the given entries could match, indexed
    for the in-memory matching _find_existing does. Fetching all candidates in a
    single query keeps previews and imports of large sets (e.g. a full-subject
    curriculum) at a constant query count instead of two queries per entry.

    Returns:
        dict: three indexes over the candidate competencies, resolved in the
        model's default ordering (first match per key wins):
        'by_source_id' maps source_id to competency; 'unsourced_by_name' maps
        lowercased name to competency for competencies without a source_id;
        'by_name' maps lowercased name to competency regardless of source_id.
    """
    source_ids = {entry['source_id'] for entry in entries if entry['source_id']}
    names_lower = {entry['name'].lower() for entry in entries}
    candidates = Competency.objects.annotate(name_lower=Lower('name')).filter(
        models.Q(source_id__in=source_ids) | models.Q(name_lower__in=names_lower)
    )

    lookup = {'by_source_id': {}, 'unsourced_by_name': {}, 'by_name': {}}
    for competency in candidates:
        _register_in_lookup(lookup, competency)
    return lookup


def _register_in_lookup(lookup, competency):
    """ Index a competency into a _build_existing_lookup dict under each key it can
    match on. setdefault keeps the first competency registered for a key, so the
    match for an ambiguous key is the first candidate in the model's default ordering.
    """
    if competency.source_id:
        lookup['by_source_id'].setdefault(competency.source_id, competency)
    else:
        lookup['unsourced_by_name'].setdefault(competency.name.lower(), competency)
    lookup['by_name'].setdefault(competency.name.lower(), competency)


def _find_existing(entry, lookup):
    """ Find the existing Competency an entry corresponds to (in the prefetched
    lookup from _build_existing_lookup), or None.

    An entry with a source_id matches on source_id first, then falls back to a
    case-insensitive name match against competencies *without* a source_id (so a
    curriculum import can adopt hand-typed competencies instead of duplicating
    them, but never hijacks a competency that belongs to a different taxonomy
    entry with the same name, e.g. the same wording in two grades' sets).

    An entry without a source_id (e.g. from a teacher-authored CSV) matches on
    name alone, keeping re-imports idempotent.
    """
    if entry['source_id']:
        return (
            lookup['by_source_id'].get(entry['source_id'])
            or lookup['unsourced_by_name'].get(entry['name'].lower())
        )
    return lookup['by_name'].get(entry['name'].lower())


def _match_entries(entries, lookup):
    """ Pair each entry with the existing Competency it corresponds to (see _find_existing).

    An unsourced competency that a sourced entry adopts leaves the name-match pool as it is
    matched, so a later entry with the same name (e.g. the same wording in another grade's
    set) can't adopt it too and overwrite the first entry's source_id and content.

    Args:
        entries (list[dict]): normalized competency-set entries, in import order.
        lookup (dict): the prefetched index from _build_existing_lookup; it is updated as
            competencies are claimed.

    Yields:
        tuple[dict, Competency | None]: each entry and its match, or None if it is new.
    """
    for entry in entries:
        existing = _find_existing(entry, lookup)
        if existing is not None and entry['source_id'] and not existing.source_id:
            lookup['unsourced_by_name'].pop(existing.name.lower(), None)
        yield entry, existing


def import_competency_set(competency_set, selected_indexes=None):
    """ Import a validated competency set into the current deck.

    The import is all or nothing: it runs in one transaction, so a failure part way
    leaves the deck as it was. Entries matching an existing competency (see
    _find_existing and _match_entries) are updated in place (never duplicated), so
    re-importing a set is idempotent. The `active` flag of existing competencies is
    left alone (deactivation is a deck-level decision that a re-import shouldn't
    quietly reverse).

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

    lookup = _build_existing_lookup(entries)
    created = updated = 0
    with transaction.atomic():
        for entry, existing in _match_entries(entries, lookup):
            if existing:
                existing.name = entry['name']
                existing.description = entry['description']
                existing.category = entry['category']
                if entry['source_id']:
                    existing.source_id = entry['source_id']
                existing.full_clean()
                existing.save()
                updated += 1
            else:
                competency = Competency(
                    name=entry['name'],
                    description=entry['description'],
                    category=entry['category'],
                    source_id=entry['source_id'] or None,
                )
                competency.full_clean()
                competency.save()
                created += 1
                # register it so a later entry in this same set matches it instead of duplicating
                _register_in_lookup(lookup, competency)
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
