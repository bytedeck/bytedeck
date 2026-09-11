"""Meta-tests that enforce this project's test-writing conventions.

Two conventions from ``CLAUDE.md`` are checked by scanning every ``test_*.py``
module's AST, a third (no em dashes) by scanning the source of the directories
listed in ``EM_DASH_CHECKED_DIRS``, and a fourth (migrations survive the deploy
window) by loading the migration graph from disk:

* **Naming**: each ``test_*`` method name follows
  ``test_method_or_class_name__specific_case_being_tested`` (i.e. contains a
  ``__`` separating the subject from the specific case).
* **Docstrings**: each ``test_*`` method, and each ``setUp`` /
  ``setUpTestData`` / ``tearDown``, has a docstring.

* **Deploy-safe migrations**: a migration adds no operation that breaks the
  version it replaces while both are briefly live (see
  ``DEPLOY_UNSAFE_OPERATIONS``).

The whole suite has been brought into conformance, so ``LEGACY_UNCONVENTIONAL``
is empty and every ``test_*.py`` is enforced. It remains as an escape hatch only:
never add entries: write conforming tests instead.
"""

import ast
import inspect
import re
from pathlib import Path

from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase

# Empty: the whole suite conforms. Keep it empty, never add entries; fix the
# test to follow the naming/docstring conventions instead.
LEGACY_UNCONVENTIONAL = set()

_SETUP_METHODS = {"setUp", "setUpTestData", "tearDown"}

# Directories under src/ scanned for em dashes. CLAUDE.md bans them project-wide, but only
# the directories named here are clear of them, so only these can be enforced. The list grows
# as others are cleared: adding a name is the last step of cleaning a directory, not the first.
EM_DASH_CHECKED_DIRS = ("questions",)

# The two spellings CLAUDE.md names. The entity is the one that hides from a plain search
# for the character, which is how three copies of one tooltip kept theirs (#2569).
_EM_DASHES = ("\u2014", "&mdash;")

# Source a check like this can read; everything else under a directory is data or binary.
_EM_DASH_SUFFIXES = (".py", ".html", ".css", ".js", ".md", ".txt")

# A line asserting an em dash is absent has to contain one to say so.
#: Written on a line that has to carry an em dash to do its job, which in practice means a
#: test asserting the character is absent from a page. The marker is what exempts the line,
#: rather than the name of the assertion on it: a line can assert an absence and still carry
#: an em dash of its own somewhere else, and that one is a violation like any other.
_EM_DASH_ALLOWED_MARKER = "em-dash-ok"

# src/ directory (this file is src/hackerspace_online/tests/test_conventions.py).
_SRC_ROOT = Path(__file__).resolve().parents[2]

# Operations that break the version they replace, for the seconds a deploy runs both.
#
# production/server-update.sh applies migrations from the new image while the previous
# containers are still serving, which is what keeps the slow part of a deploy out of the
# downtime window (#2631). The cost is that the outgoing code meets the new schema. Django
# SELECTs every concrete field of a model by default, so dropping or renaming a column the
# outgoing version still has in its own model class makes its ordinary queries raise
# ProgrammingError until it is replaced. With six uwsgi workers serving live traffic, that is
# real requests failing, not a theoretical race.
#
# Only operations that are unsafe *whatever* the surrounding code does are listed. AddField
# and AlterField can be unsafe too (a NOT NULL column with no default, or tightening an
# existing column's nullability, both break the outgoing version's INSERTs), but they are
# usually fine, and telling the two apart means diffing model state rather than reading a
# list of operations. They are documented in CONTRIBUTING.md and deliberately not automated
# here: a check that cries wolf on the common case would only teach people to skip it.
DEPLOY_UNSAFE_OPERATIONS = frozenset({
    "RemoveField",
    "RenameField",
    "RenameModel",
    "DeleteModel",
})

# Migrations that predate the check, listed so it can be enforced from here on rather than
# waiting for the history to be rewritten (which it cannot be: these are long applied).
#
# Never add entries. A new migration needing one of these operations goes through
# CONTRIBUTING.md's two-release drop instead, or, where that genuinely does not apply, carries
# a `deploy-unsafe-ok` marker saying why.
LEGACY_DEPLOY_UNSAFE_MIGRATIONS = frozenset({
    "badges/0010_auto_20200901_1505",
    "badges/0015_rename_active_badge_published",
    "courses/0004_remove_coursestudent_grade",
    "courses/0008_auto_20190815_2253",
    "courses/0011_remove_semester_number",
    "courses/0017_remove_semester_active",
    "courses/0022_auto_20220811_1743",
    "courses/0026_delete_datetype_model",
    "courses/0029_semester_status",
    "djcytoscape/0008_auto_20200705_1904",
    "djcytoscape/0009_auto_20200705_1906",
    "djcytoscape/0010_remove_cytoscape_container_element_id",
    "profile_manager/0011_remove_profile_student_number",
    "profile_manager/0013_auto_20200818_1355",
    "profile_manager/0018_auto_20240107_1115",
    "profile_manager/0019_auto_20240807_1432",
    "profile_manager/0021_remove_profile_intro_tour_completed",
    "quest_manager/0009_auto_20190807_1525",
    "quest_manager/0011_auto_20200105_2257",
    "quest_manager/0018_auto_20200818_1356_squashed_0019_auto_20200818_1357",
    "quest_manager/0038_remove_questsubmission_draft_text",
    "quest_manager/0045_rename_visible_to_students_to_published",
    "quest_manager/0047_rename_category_active_to_published",
    "siteconfig/0002_auto_20200402_2201",
    "siteconfig/0004_auto_20200402_2233",
    "siteconfig/0017_auto_20220812_1554",
    "siteconfig/0032_remove_siteconfig_enable_submission_questions",
    "tenant/0007_django_tenants_migration",
    "tenant/0025_remove_tenant_max_quests_remove_tenant_owner_email_and_more",
})

#: Written in a migration whose unsafe operation is deliberate and cannot hurt a deploy: a
#: table nothing has ever queried in production, say. Spelled ``deploy-unsafe-ok: <reason>``,
#: and the reason is required rather than conventional: the whole point of the check is that
#: "I am sure it is fine" is the reasoning that breaks a class mid-lesson, so a bare marker
#: exempts nothing. Matched anywhere in the file, since it belongs in a comment next to the
#: operation it excuses.
_DEPLOY_UNSAFE_ALLOWED_MARKER = re.compile(r"deploy-unsafe-ok:[ \t]*\S+")


def _iter_project_migrations():
    """Yield ``("<app>/<name>", Migration, Path)`` for every migration under src/.

    Third-party migrations (Django's own, allauth's, django_celery_beat's) load into the same
    graph and are excluded by path: their contents are not ours to change, so flagging them
    would only mean listing them as legacy forever.
    """
    loader = MigrationLoader(connection=None, ignore_no_migrations=True)
    for (app_label, name), migration in sorted(loader.disk_migrations.items()):
        try:
            path = Path(inspect.getfile(type(migration))).resolve()
        except TypeError:  # pragma: no cover - a migration built in memory has no file
            continue
        if not path.is_relative_to(_SRC_ROOT):
            continue
        yield f"{app_label}/{name}", migration, path


def _deploy_unsafe_operations(migration):
    """Return ``["<Operation> on <target>"]`` for each deploy-unsafe operation in ``migration``.

    Args:
        migration (Migration): the loaded migration to inspect.

    Returns:
        list[str]: one entry per offending operation, empty when the migration is safe.
    """
    problems = []
    for operation in migration.operations:
        problems.extend(_unsafe_within(operation))
    return problems


def _unsafe_within(operation, prefix=""):
    """Return the deploy-unsafe descriptions in ``operation``, looking inside wrappers.

    ``SeparateDatabaseAndState`` is how CONTRIBUTING.md's two-release drop separates the
    model change from the column change, so it needs opening rather than skipping. Only its
    ``database_operations`` are examined: those touch real columns, while ``state_operations``
    only tell Django the field is gone, which is the safe half and the whole point of release
    one. A wrapper carrying a destructive operation in *both* halves is a plain destructive
    migration wearing a hat, and is reported like one.

    Args:
        operation (Operation): the migration operation to inspect.
        prefix (str): how to label a nested operation in the report.

    Returns:
        list[str]: one entry per offending operation, empty when there is nothing unsafe.
    """
    name = type(operation).__name__
    if name == "SeparateDatabaseAndState":
        problems = []
        for inner in operation.database_operations:
            problems.extend(_unsafe_within(inner, prefix="SeparateDatabaseAndState.database_operations -> "))
        return problems
    if name not in DEPLOY_UNSAFE_OPERATIONS:
        return []
    # Every one of these names a model, and all but DeleteModel name a field too.
    target = getattr(operation, "model_name", None) or getattr(operation, "name", "?")
    field = getattr(operation, "old_name", None) or getattr(operation, "name", None)
    described = f"{name} on {target}.{field}" if field and field != target else f"{name} on {target}"
    return [prefix + described]


def _iter_test_modules():
    """Yield (repo-relative-str, Path) for every ``test_*.py`` under src/."""
    for path in sorted(_SRC_ROOT.rglob("test_*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path.relative_to(_SRC_ROOT).as_posix(), path


def _violations(path):
    """Return a list of human-readable convention violations in ``path``."""
    problems = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if node.name.startswith("test"):
            if "__" not in node.name:
                problems.append(f"{node.name}: name lacks '__' (test_subject__case)")
            if not ast.get_docstring(node):
                problems.append(f"{node.name}: missing docstring")
        elif node.name in _SETUP_METHODS and not ast.get_docstring(node):
            problems.append(f"{node.name}: missing docstring")
    return problems


def _em_dash_violations(path):
    """Return ``["<line no>: <line>"]`` for each line of ``path`` carrying an em dash.

    Args:
        path (Path): the source file to scan.

    Returns:
        list[str]: one entry per offending line, empty when the file is clean.
    """
    problems = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if _EM_DASH_ALLOWED_MARKER in line:
            continue
        if any(dash in line for dash in _EM_DASHES):
            problems.append(f"{number}: {line.strip()}")
    return problems


def _iter_em_dash_sources():
    """Yield (repo-relative-str, Path) for every source file under ``EM_DASH_CHECKED_DIRS``."""
    for directory in EM_DASH_CHECKED_DIRS:
        for path in sorted((_SRC_ROOT / directory).rglob("*")):
            if not path.is_file() or path.suffix not in _EM_DASH_SUFFIXES:
                continue
            if "__pycache__" in path.parts or "migrations" in path.parts:
                continue
            yield path.relative_to(_SRC_ROOT).as_posix(), path


class TestNoEmDashes(SimpleTestCase):
    """Guard for CLAUDE.md's ban on em dashes, over the directories cleared of them."""

    def test_conventions__checked_directories_have_no_em_dashes(self):
        """No source file in EM_DASH_CHECKED_DIRS contains an em dash, in either spelling.

        The rule covers comments and docstrings as much as anything a user reads, so this
        scans lines rather than only rendered strings. A line that genuinely has to carry the
        character, such as one asserting a page does not contain it, says so with an
        ``em-dash-ok`` marker and is skipped.
        """
        failures = {}
        for rel, path in _iter_em_dash_sources():
            problems = _em_dash_violations(path)
            if problems:
                failures[rel] = problems
        self.assertEqual(
            failures, {},
            "Em dashes found (CLAUDE.md: use a colon for a substatement, or brackets for a "
            "parenthetical aside):\n"
            + "\n".join(f"{f}:\n  " + "\n  ".join(v) for f, v in failures.items()),
        )


class TestMigrationsSurviveTheDeployWindow(SimpleTestCase):
    """Guard that a new migration cannot break the version it replaces mid-deploy."""

    def test_conventions__new_migrations_carry_no_deploy_unsafe_operation(self):
        """No migration outside LEGACY_DEPLOY_UNSAFE_MIGRATIONS drops or renames a column.

        A deploy applies migrations from the new image while the previous containers are
        still serving (#2631), so for those seconds the outgoing code queries the new schema.
        Django SELECTs every concrete field of a model, so a column it still knows about and
        no longer finds raises ProgrammingError on ordinary reads. CONTRIBUTING.md's
        two-release drop is how to remove one without that window; a migration that genuinely
        cannot hurt a deploy says so with a ``deploy-unsafe-ok`` marker and a reason.
        """
        failures = {}
        for rel, migration, path in _iter_project_migrations():
            if rel in LEGACY_DEPLOY_UNSAFE_MIGRATIONS:
                continue
            if _DEPLOY_UNSAFE_ALLOWED_MARKER.search(path.read_text(encoding="utf-8")):
                continue
            problems = _deploy_unsafe_operations(migration)
            if problems:
                failures[rel] = problems
        self.assertEqual(
            failures, {},
            "Migrations that would break the outgoing version during a deploy. Use the "
            "two-release drop in CONTRIBUTING.md ('Migrations and the deploy window') rather "
            "than adding to LEGACY_DEPLOY_UNSAFE_MIGRATIONS:\n"
            + "\n".join(f"{f}:\n  " + "\n  ".join(v) for f, v in failures.items()),
        )

    def test_legacy_migration_list__has_no_stale_entries(self):
        """Every LEGACY_DEPLOY_UNSAFE_MIGRATIONS entry still exists and is still unsafe.

        Migrations are not edited once applied, so an entry going stale means one was renamed,
        squashed away or deleted. Catching that keeps the list from quietly growing into a
        place where a real violation could hide behind a name nothing checks any more.
        """
        known = {rel: migration for rel, migration, _ in _iter_project_migrations()}
        stale = []
        for rel in sorted(LEGACY_DEPLOY_UNSAFE_MIGRATIONS):
            if rel not in known:
                stale.append(f"{rel}: migration no longer exists")
            elif not _deploy_unsafe_operations(known[rel]):
                stale.append(f"{rel}: is now safe, remove it from LEGACY_DEPLOY_UNSAFE_MIGRATIONS")
        self.assertEqual(stale, [], "Stale LEGACY_DEPLOY_UNSAFE_MIGRATIONS entries:\n  " + "\n  ".join(stale))


class TestNamingAndDocstringConventions(SimpleTestCase):
    """Guard that enforces test naming + docstring conventions on non-legacy modules."""

    def test_conventions__non_legacy_modules_conform(self):
        """Every test module not in LEGACY_UNCONVENTIONAL conforms to the conventions."""
        failures = {}
        for rel, path in _iter_test_modules():
            if rel in LEGACY_UNCONVENTIONAL:
                continue
            problems = _violations(path)
            if problems:
                failures[rel] = problems
        self.assertEqual(
            failures, {},
            "Test convention violations found (add docstrings / rename to "
            "test_subject__case). Fix them rather than adding to LEGACY_UNCONVENTIONAL:\n"
            + "\n".join(f"{f}:\n  " + "\n  ".join(v) for f, v in failures.items()),
        )

    def test_legacy_list__has_no_stale_entries(self):
        """Every LEGACY_UNCONVENTIONAL entry still exists and still violates (keeps the list honest)."""
        stale = []
        for rel in sorted(LEGACY_UNCONVENTIONAL):
            path = _SRC_ROOT / rel
            if not path.exists():
                stale.append(f"{rel}: file no longer exists")
            elif not _violations(path):
                stale.append(f"{rel}: now conforms, remove it from LEGACY_UNCONVENTIONAL")
        self.assertEqual(stale, [], "Stale LEGACY_UNCONVENTIONAL entries:\n  " + "\n  ".join(stale))
