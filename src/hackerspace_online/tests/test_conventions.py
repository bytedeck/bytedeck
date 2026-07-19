"""Meta-tests that enforce this project's test-writing conventions.

Two conventions from ``CLAUDE.md`` are checked by scanning every ``test_*.py``
module's AST:

* **Naming** — each ``test_*`` method name follows
  ``test_method_or_class_name__specific_case_being_tested`` (i.e. contains a
  ``__`` separating the subject from the specific case).
* **Docstrings** — each ``test_*`` method, and each ``setUp`` /
  ``setUpTestData`` / ``tearDown``, has a docstring.

Legacy modules that predate these conventions are listed in
``LEGACY_UNCONVENTIONAL`` and skipped, so this guard fails only on *new or
touched* files that don't conform. The list is a burn-down: as an app's tests
are cleaned up, remove its modules here and this guard locks them in. Do not add
new entries — write conforming tests instead.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

# Repo-relative (to src/) modules still awaiting a conventions cleanup. SHRINK
# THIS LIST — never grow it. When you clean an app's tests, delete its entries.
LEGACY_UNCONVENTIONAL = {
    "announcements/tests/test_models.py",
    "announcements/tests/test_signals.py",
    "announcements/tests/test_tasks.py",
    "announcements/tests/test_views.py",
    "badges/tests/test_forms.py",
    "badges/tests/test_models.py",
    "badges/tests/test_views.py",
    "bytedeck_summernote/tests/test_admin.py",
    "bytedeck_summernote/tests/test_css_sanitizier.py",
    "bytedeck_summernote/tests/test_views.py",
    "bytedeck_summernote/tests/test_widgets.py",
    "comments/tests/test_models.py",
    "comments/tests/test_views.py",
    "courses/tests/test_models.py",
    "courses/tests/test_views.py",
    "djcytoscape/tests/test_fields.py",
    "djcytoscape/tests/test_models.py",
    "djcytoscape/tests/test_signals.py",
    "djcytoscape/tests/test_tasks.py",
    "djcytoscape/tests/test_views.py",
    "hackerspace_online/tests/test_auth.py",
    "hackerspace_online/tests/test_celery.py",
    "hackerspace_online/tests/test_celerybeat_signals.py",
    "hackerspace_online/tests/test_forms.py",
    "hackerspace_online/tests/test_management_commands.py",
    "hackerspace_online/tests/test_middleware.py",
    "hackerspace_online/tests/test_settings.py",
    "hackerspace_online/tests/test_shell_utils.py",
    "hackerspace_online/tests/test_signals.py",
    "hackerspace_online/tests/test_utils.py",
    "hackerspace_online/tests/test_views.py",
    "library/tests/test_utils.py",
    "library/tests/test_views.py",
    "notifications/tests/test_models.py",
    "notifications/tests/test_tasks.py",
    "notifications/tests/test_views.py",
    "portfolios/tests/test_views.py",
    "prerequisites/tests/test_fields.py",
    "prerequisites/tests/test_forms.py",
    "prerequisites/tests/test_models.py",
    "prerequisites/tests/test_signals.py",
    "profile_manager/tests/test_forms.py",
    "profile_manager/tests/test_managers.py",
    "profile_manager/tests/test_models.py",
    "profile_manager/tests/test_tasks.py",
    "profile_manager/tests/test_views.py",
    "quest_manager/tests/test_forms.py",
    "quest_manager/tests/test_managers.py",
    "quest_manager/tests/test_models.py",
    "quest_manager/tests/test_signals.py",
    "quest_manager/tests/test_views.py",
    "siteconfig/tests/test_forms.py",
    "siteconfig/tests/test_models.py",
    "siteconfig/tests/test_views.py",
    "tags/tests/test_models.py",
    "tags/tests/test_views.py",
    "tags/tests/test_widgets.py",
    "tenant/tests/test_admin.py",
    "tenant/tests/test_forms.py",
    "tenant/tests/test_initialization.py",
    "tenant/tests/test_models.py",
    "tenant/tests/test_schema_aware_user_delete.py",
    "tenant/tests/test_tasks.py",
    "tenant/tests/test_views.py",
    "utilities/tests/test_fields.py",
    "utilities/tests/test_forms.py",
    "utilities/tests/test_html.py",
    "utilities/tests/test_templatetags_filters.py",
    "utilities/tests/test_views.py",
    "utilities/tests/test_widgets.py",
}

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
