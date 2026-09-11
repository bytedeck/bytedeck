#!/usr/bin/env bash
# Run the ruff that requirements.txt pins, refusing to run a different one.
#
# The pre-commit hook uses this rather than pinning its own copy of ruff, so
# requirements.txt stays the only place the version is named. `language: system`
# resolves ruff from PATH, which is the project venv for anyone following the
# setup in README.md, but not necessarily: a ruff from somewhere else on PATH
# would lint with a different rule set than CI, and the disagreement would only
# show up as a CI failure on a commit that passed locally. Comparing the
# executable against the requirement turns that into an error here instead.
set -euo pipefail

requirement=$(grep -m1 -E '^ruff([<>=!~,]|$)' requirements.txt | cut -d'#' -f1 | tr -d '[:space:]')
pinned=${requirement#ruff==}

if ! command -v ruff > /dev/null; then
    echo "ruff is not on PATH. Activate the project venv (see README.md), or: pip install -r requirements.txt" >&2
    exit 1
fi

installed=$(ruff --version | awk '{print $2}')

# Only an exact pin gives a version to compare against; a range is satisfied by
# more than one release, so there is nothing to enforce here and CI's install
# from the same line remains the reference.
if [ "$pinned" != "$requirement" ] && [ "$pinned" != "$installed" ]; then
    echo "ruff $installed is on PATH, but requirements.txt pins $pinned." >&2
    echo "CI lints with $pinned, so this commit could pass here and fail there. Install the pinned version:" >&2
    echo "    pip install -r requirements.txt" >&2
    exit 1
fi

exec ruff check --force-exclude --fix "$@"
