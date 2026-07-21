#!/usr/bin/env bash
#
# UserPromptSubmit hook: keep long-running Claude Code sessions from acting on a
# STALE copy of CLAUDE.md.
#
# CLAUDE.md is read into a session's context once, at session start, and is NOT
# re-read when the file changes on disk. So a session that's been open across a
# CLAUDE.md edit keeps following the old version. This hook re-injects the file's
# current contents (as extra context for the turn) the first time it notices the
# file changed since this particular session last saw it.
#
# Design notes:
#   - Per session: state is keyed by session_id, so two concurrent sessions each
#     get the update (a single shared marker would let the first session swallow
#     it for the others).
#   - mtime-gated: on the common case (file unchanged) it does a couple of stats
#     and emits nothing -- negligible cost per prompt.
#   - Fail-open: any error exits 0 with no output, so a broken hook can never
#     block you from submitting a prompt.
#
# stdout on exit 0 from a UserPromptSubmit hook is added to the model's context
# for that turn; that's how the refreshed CLAUDE.md reaches the assistant.

# --- fail open no matter what ------------------------------------------------
fail_open() { exit 0; }
trap fail_open EXIT

payload="$(cat 2>/dev/null || true)"          # hook receives JSON on stdin
proj="${CLAUDE_PROJECT_DIR:-$PWD}"
md="$proj/CLAUDE.md"
[ -f "$md" ] || exit 0

# session_id from the payload; bail quietly if we can't get it (need python3).
command -v python3 >/dev/null 2>&1 || exit 0
sid="$(printf '%s' "$payload" | python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("session_id", ""))
except Exception:
    pass' 2>/dev/null || true)"
sid="$(printf '%s' "$sid" | tr -cd 'A-Za-z0-9_-')"   # sanitize for a filename
[ -n "$sid" ] || exit 0

cache_dir="$proj/.claude/.cache"
mkdir -p "$cache_dir" 2>/dev/null || exit 0
state="$cache_dir/claude_md_mtime.$sid"

# Current mtime (GNU stat, then BSD stat, then give up).
cur="$(stat -c %Y "$md" 2>/dev/null || stat -f %m "$md" 2>/dev/null || echo '')"
[ -n "$cur" ] || exit 0
prev="$(cat "$state" 2>/dev/null || echo '')"
printf '%s' "$cur" > "$state" 2>/dev/null || true

# First time this session runs the hook: the session already loaded CLAUDE.md at
# startup, so just record the mtime and inject nothing.
[ -n "$prev" ] || exit 0

# Unchanged since we last checked: nothing to do.
[ "$cur" = "$prev" ] && exit 0

# Changed: re-inject the current contents.
printf 'NOTE: CLAUDE.md was edited on disk after this session started, so the copy loaded into your context is stale. Its current contents are below and supersede any earlier copy — follow this version for the rest of the session.\n\n===== BEGIN CURRENT CLAUDE.md =====\n'
cat "$md" 2>/dev/null || true
printf '\n===== END CURRENT CLAUDE.md =====\n'
exit 0
