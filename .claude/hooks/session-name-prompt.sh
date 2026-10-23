#!/usr/bin/env bash
#
# SessionStart hook: a Claude Code session cannot read its own human-readable
# name (only the opaque session_... id is in context). CLAUDE.md asks sessions to
# sign GitHub posts with that readable name, so this hook tries to SUPPLY the name
# without a human in the loop, and only falls back to asking when it can't.
#
# Resolution order (first hit wins):
#   1. $CLAUDE_SESSION_NAME env var, if the harness/environment provides one.
#   2. A per-session cache file .claude/.cache/session_name.<session_id> that the
#      user (or tooling) can drop in -- mirrors the mtime-cache pattern used by
#      reload-claude-md.sh. Once written, resumes of the same session inject the
#      name directly and never re-ask.
#   3. Fall back to instructing the session to ask the user once (the old
#      behavior), phrased conditionally so resume/compaction don't re-ask.
#
# The fallback also tells the session, once it learns its name, to persist it to
# the cache file for this session_id so subsequent turns/resumes skip the ask.
#
# stdout on exit 0 from a SessionStart hook is added to the session's context.

trap 'exit 0' EXIT   # fail open: never disrupt session startup

payload="$(cat 2>/dev/null || true)"          # SessionStart hook receives JSON on stdin
proj="${CLAUDE_PROJECT_DIR:-$PWD}"

# Normalize a candidate name to a bounded, single-line, control-char-free value:
# strip ASCII control chars (NUL, tab, CR, LF, ...), trim surrounding whitespace,
# and cap the length. A whitespace-only or garbage value therefore collapses to
# empty so the fallback prompt still fires, instead of injecting an unusable
# sign-off like "- Claude Code (   )".
normalize_name() {
    printf '%s' "$1" | tr -d '\000-\037\177' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' | head -c 200
}

# --- 1. explicit env var ------------------------------------------------------
name="$(normalize_name "${CLAUDE_SESSION_NAME:-}")"

# --- resolve session_id (needed for the cache path and the persist hint) ------
sid=""
if command -v python3 >/dev/null 2>&1; then
    sid="$(printf '%s' "$payload" | python3 -c 'import sys, json
try:
    print(json.load(sys.stdin).get("session_id", ""))
except Exception:
    pass' 2>/dev/null || true)"
    sid="$(printf '%s' "$sid" | tr -cd 'A-Za-z0-9_-')"   # sanitize for a filename
fi

# --- 2. per-session cache file ------------------------------------------------
cache=""
if [ -n "$sid" ]; then
    cache="$proj/.claude/.cache/session_name.$sid"
    if [ -z "$name" ] && [ -f "$cache" ]; then
        name="$(normalize_name "$(head -c 200 "$cache" 2>/dev/null || true)")"
    fi
fi

# --- name known: inject it directly, no human turn needed ---------------------
if [ -n "$name" ]; then
    printf 'SESSION NAME: This session is named "%s". Per CLAUDE.md, sign everything you post to GitHub with "- Claude Code (%s)". Use it directly; do not ask the user for it.\n' "$name" "$name"
    exit 0
fi

# --- 3. fall back to asking the user once -------------------------------------
if [ -n "$cache" ]; then
    printf 'SESSION NAME: This session does not automatically know its own human-readable name (only its session_... id). Per CLAUDE.md, GitHub posts are signed with the readable session name. So, unless the user has already told you this session'"'"'s name in this conversation, ask them once near the start -- e.g. "What should I use as this session'"'"'s name when I sign GitHub posts?" -- and use their answer in sign-offs for the rest of the session. Once you learn it, persist it so future turns/resumes skip this: write just the name to %s (create the .claude/.cache/ dir if needed).\n' "$cache"
else
    cat <<'EOF'
SESSION NAME: This session does not automatically know its own human-readable
name (only its session_... id). Per CLAUDE.md, GitHub posts are signed with the
readable session name. So, unless the user has already told you this session's
name in this conversation, ask them once near the start -- e.g. "What should I
use as this session's name when I sign GitHub posts?" -- and use their answer in
sign-offs for the rest of the session.
EOF
fi
exit 0
