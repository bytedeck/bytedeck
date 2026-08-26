"""Meta-tests that enforce this project's test-writing conventions.

Two conventions from ``CLAUDE.md`` are checked by scanning every ``test_*.py``
module's AST, and a third (no em dashes) by scanning the source of the
directories listed in ``EM_DASH_CHECKED_DIRS``:

* **Naming**: each ``test_*`` method name follows
  ``test_method_or_class_name__specific_case_being_tested`` (i.e. contains a
  ``__`` separating the subject from the specific case).
* **Docstrings**: each ``test_*`` method, and each ``setUp`` /
  ``setUpTestData`` / ``tearDown``, has a docstring.

The whole suite has been brought into conformance, so ``LEGACY_UNCONVENTIONAL``
is empty and every ``test_*.py`` is enforced. It remains as an escape hatch only:
never add entries: write conforming tests instead.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

# Empty: the whole suite conforms. Keep it empty, never add entries; fix the
# test to follow the naming/docstring conventions instead.
LEGACY_UNCONVENTIONAL = set()

_SETUP_METHODS = {"setUp", "setUpTestData", "tearDown"}

# Directories under src/ scanned for em dashes. CLAUDE.md bans them project-wide, but the
# rest of the tree still carries a backlog (102 more, across 35 files, when #2569 was written), so
# this starts at the app that has been cleared and grows as others are. Adding a name here
# is the last step of cleaning a directory, not the first.
EM_DASH_CHECKED_DIRS = ("questions",)

# The two spellings CLAUDE.md names. The entity is the one that hides from a plain search
# for the character, which is how three copies of one tooltip kept theirs (#2569).
_EM_DASHES = ("\u2014", "&mdash;")

# Source a check like this can read; everything else under a directory is data or binary.
_EM_DASH_SUFFIXES = (".py", ".html", ".css", ".js", ".md", ".txt")

# A line asserting an em dash is absent has to contain one to say so.
_ASSERTS_ABSENCE = ("assertNotContains", "assertNotIn")

# src/ directory (this file is src/hackerspace_online/tests/test_conventions.py).
_SRC_ROOT = Path(__file__).resolve().parents[2]


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
        if any(marker in line for marker in _ASSERTS_ABSENCE):
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
        scans lines rather than only rendered strings. A line asserting an em dash is absent
        is skipped, since it has to name one to do that.
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
