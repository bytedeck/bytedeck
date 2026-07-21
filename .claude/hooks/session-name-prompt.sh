#!/usr/bin/env bash
#
# SessionStart hook: a Claude Code session cannot read its own human-readable
# name (only the opaque session_... id is in context). CLAUDE.md asks sessions to
# sign GitHub posts with that readable name, so this hook injects an instruction
# telling the session to ask the user for its name.
#
# It's phrased conditionally ("if you don't already know it"), so on resume /
# compaction -- where the name is already in the conversation history -- the
# assistant simply won't re-ask.
#
# stdout on exit 0 from a SessionStart hook is added to the session's context.

trap 'exit 0' EXIT   # fail open: never disrupt session startup

cat <<'EOF'
SESSION NAME: This session does not automatically know its own human-readable
name (only its session_... id). Per CLAUDE.md, GitHub posts are signed with the
readable session name. So, unless the user has already told you this session's
name in this conversation, ask them once near the start -- e.g. "What should I
use as this session's name when I sign GitHub posts?" -- and use their answer in
sign-offs for the rest of the session.
EOF
exit 0
