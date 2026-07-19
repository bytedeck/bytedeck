"""Meta-tests that enforce this project's test-writing conventions.

Two conventions from ``CLAUDE.md`` are checked by scanning every ``test_*.py``
module's AST:

* **Naming** — each ``test_*`` method name follows
  ``test_method_or_class_name__specific_case_being_tested`` (i.e. contains a
  ``__`` separating the subject from the specific case).
* **Docstrings** — each ``test_*`` method, and each ``setUp`` /
  ``setUpTestData`` / ``tearDown``, has a docstring.

The whole suite has been brought into conformance, so ``LEGACY_UNCONVENTIONAL``
is empty and every ``test_*.py`` is enforced. It remains as an escape hatch only:
never add entries — write conforming tests instead.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

# Empty: the whole suite conforms. Keep it empty — never add entries; fix the
# test to follow the naming/docstring conventions instead.
LEGACY_UNCONVENTIONAL = set()

_SETUP_METHODS = {"setUp", "setUpTestData", "tearDown"}

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
                stale.append(f"{rel}: now conforms — remove it from LEGACY_UNCONVENTIONAL")
        self.assertEqual(stale, [], "Stale LEGACY_UNCONVENTIONAL entries:\n  " + "\n  ".join(stale))
