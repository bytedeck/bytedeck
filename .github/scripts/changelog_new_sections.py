#!/usr/bin/env python3
"""Detect newly-added CHANGELOG version sections and build a discussion post.

Run by the ``announce-changelog`` workflow when ``CHANGELOG.md`` changes on the
``master`` branch. It compares the current ``CHANGELOG.md`` against its state at
the commit before the push (``BEFORE_SHA``) and, for every ``### [x.y.z]`` version
heading that is present now but was not present then, extracts that whole section
verbatim. Those sections become the body of a single GitHub Discussion
announcement, so a release that reaches production is posted once and never
re-posted on later pushes.

Outputs (for the workflow):
  * ``discussion_body.md`` : the post body (new sections, oldest first), if any.
  * ``$GITHUB_OUTPUT`` gets ``has_new`` (true/false) and, when true, ``title``
    plus ``versions`` (the announced version numbers, comma-separated, ascending)
    for the workflow's per-version duplicate guard.

Env:
  * ``BEFORE_SHA``   : the ``github.event.before`` commit to diff against. An
                       all-zeros SHA (a force-push / rewritten history) or an
                       unreachable commit means there is no reliable baseline; in
                       that case only the single newest changelog section is
                       announced (never the whole history), and the workflow's
                       per-version duplicate guard prevents a repost.
  * ``CHANGELOG``    : path to the changelog (default ``CHANGELOG.md``).
  * ``GITHUB_OUTPUT``: set by Actions; if absent (local testing) it is skipped.
"""

import os
import re
import subprocess
import sys

# Matches a version heading like "### [1.30.0] 2026-08-01 Claude II" and
# captures the semantic version. Only headings of this exact shape delimit a
# release section; anything else in the file is section content.
HEADER_RE = re.compile(r"^### \[(\d+\.\d+\.\d+)\]")

CHANGELOG = os.environ.get("CHANGELOG", "CHANGELOG.md")


def read_current(path):
    """Return the working-tree changelog text, or '' if it can't be read."""
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def read_old(before_sha, path):
    """Return ``(available, text)`` for the changelog at ``before_sha``.

    ``available`` is False when there is no reliable baseline to diff against:
    an all-zero SHA (GitHub's sentinel for "no previous commit", e.g. a
    force-push that rewrites history or a freshly created ref) or a git error
    (the commit is unreachable, or the file did not exist there). The caller
    must not treat an unavailable baseline as "empty old changelog": doing so
    would mark every historical version as new and flood the discussion. When
    True, ``text`` is the changelog exactly as it was at that commit.
    """
    if not before_sha or set(before_sha) == {"0"}:
        return False, ""
    try:
        text = subprocess.check_output(
            ["git", "show", f"{before_sha}:{path}"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return True, text
    except subprocess.CalledProcessError:
        return False, ""


def parse_sections(text):
    """Split changelog text into an ordered list of (version, section_text).

    ``section_text`` runs from a version heading up to (but not including) the
    next version heading, with trailing blank lines stripped. Content before the
    first heading (the file's intro) is ignored.
    """
    lines = text.splitlines()
    sections = []
    current_version = None
    current_lines = []

    def flush():
        if current_version is not None:
            # Drop trailing blank lines so joined sections space evenly.
            body = "\n".join(current_lines).rstrip("\n")
            sections.append((current_version, body))

    for line in lines:
        match = HEADER_RE.match(line)
        if match:
            flush()
            current_version = match.group(1)
            current_lines = [line]
        elif current_version is not None:
            current_lines.append(line)
    flush()
    return sections


def version_key(version):
    """Sort key turning '1.30.0' into (1, 30, 0) for chronological ordering."""
    return tuple(int(part) for part in version.split("."))


def format_title(versions):
    """Build the announcement title from the new version numbers (ascending).

    One version -> "(1.30.0)"; two -> "(1.30.0 and 1.31.0)"; three or more ->
    "(1.30.0, 1.31.0, and 1.32.0)". Mirrors the wording of past announcements.
    """
    ordered = sorted(versions, key=version_key)
    if len(ordered) == 1:
        joined = ordered[0]
    elif len(ordered) == 2:
        joined = f"{ordered[0]} and {ordered[1]}"
    else:
        joined = ", ".join(ordered[:-1]) + f", and {ordered[-1]}"
    return f"Bytedeck App Updates ({joined})"


def write_output(name, value):
    """Append a ``name=value`` line to $GITHUB_OUTPUT if the runner set it."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as fh:
        fh.write(f"{name}={value}\n")


def main():
    before_sha = os.environ.get("BEFORE_SHA", "")
    new_text = read_current(CHANGELOG)
    available, old_text = read_old(before_sha, CHANGELOG)
    new_sections = parse_sections(new_text)

    if available:
        # Normal path: announce every version present now but not at BEFORE_SHA,
        # ordered oldest-first so a multi-version catch-up post reads
        # chronologically.
        old_versions = {version for version, _ in parse_sections(old_text)}
        added = [(v, body) for v, body in new_sections if v not in old_versions]
    elif new_sections:
        # No reliable baseline (force-push / rewritten history): fall back to
        # announcing only the single newest release section rather than the whole
        # changelog. The workflow's duplicate-title guard still prevents a repost
        # if that version was already announced.
        added = [max(new_sections, key=lambda item: version_key(item[0]))]
        print("No reliable baseline; falling back to newest section only.")
    else:
        added = []
    added.sort(key=lambda item: version_key(item[0]))

    if not added:
        write_output("has_new", "false")
        print("No new changelog version sections detected.")
        return

    versions = [v for v, _ in added]
    body = "\n\n\n".join(section for _, section in added).rstrip("\n") + "\n"
    with open("discussion_body.md", "w", encoding="utf-8") as fh:
        fh.write(body)

    title = format_title(versions)
    write_output("has_new", "true")
    write_output("title", title)
    write_output("versions", ",".join(versions))
    print(f"New version(s) detected: {', '.join(versions)}")
    print(f"Discussion title: {title}")


if __name__ == "__main__":
    sys.exit(main())
