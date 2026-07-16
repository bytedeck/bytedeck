#!/bin/sh
# Idempotent setup of the GitHub Actions self-hosted deploy runner on this host.
#
# Called from server-update.sh on every deploy, and safe to run directly:
#   - If the runner is already configured and its service is running (and the
#     SETUP_VERSION marker matches), it prints one line and exits.
#   - If a runner was configured manually, it is adopted as-is (service checked,
#     marker stamped) rather than reinstalled.
#   - If no runner exists and the shell is interactive, it offers to set one up,
#     prompting for the short-lived registration token from GitHub.
#   - If no runner exists and the shell is NOT interactive (e.g. running under
#     the deploy runner itself), it prints a hint and exits 0 -- deploys must
#     never fail on this.
#
# The runner LABEL is derived from ROOT_DOMAIN in .env: bytedeck.com ->
# "production", anything else -> "staging" (matching deploy.yml's runs-on).
# The runner binary self-updates after installation, so SETUP_VERSION tracks
# only *our* setup shape (labels, service user, install dir); bump it when
# those requirements change to force a re-run on the hosts.
set -e

SETUP_VERSION="1"

# Operate from the repo root regardless of caller CWD (matches server-update.sh).
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

RUNNER_DIR="${RUNNER_DIR:-$HOME/actions-runner}"
MARKER="$RUNNER_DIR/.bytedeck-runner-setup-version"
REPO_URL="https://github.com/bytedeck/bytedeck"

svc() {
    # Always run svc.sh with the systemd pager disabled: svc.sh shells out to
    # `systemctl status`, which on a TTY opens an interactive pager (less) and
    # freezes the deploy until 'q' is pressed. An empty SYSTEMD_PAGER is
    # equivalent to systemctl --no-pager.
    (cd "$RUNNER_DIR" && sudo env SYSTEMD_PAGER= SYSTEMD_LESS= ./svc.sh "$@")
}

service_running() {
    # svc.sh proxies systemctl status: exit 0 = active.
    svc status >/dev/null 2>&1
}

# --- Fast path: already set up and current ----------------------------------
if [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$SETUP_VERSION" ]; then
    if service_running; then
        echo "Deploy runner: already set up (v$SETUP_VERSION) and running -- skipping."
        exit 0
    fi
    echo "Deploy runner: configured but service not running -- starting it."
    svc start
    exit 0
fi

# --- Adopt a runner that was configured manually -----------------------------
if [ -f "$RUNNER_DIR/.runner" ]; then
    echo "Deploy runner: existing configuration found in $RUNNER_DIR -- adopting it."
    service_running || svc start
    echo "$SETUP_VERSION" > "$MARKER"
    exit 0
fi

# --- Not set up: only proceed if a human is at the terminal ------------------
if [ ! -t 0 ]; then
    echo "Deploy runner: NOT set up on this host. Run ./production/setup-runner.sh"
    echo "interactively (or follow SERVER-README.md -> 'Automated deploys') to enable"
    echo "automated deploys. Continuing without it."
    exit 0
fi

# Derive the label from this host's .env so prod/staging need no prompt.
ROOT_DOMAIN="$(sed -n 's/^ROOT_DOMAIN=//p' "$REPO_ROOT/.env" 2>/dev/null | tail -1)"
if [ "$ROOT_DOMAIN" = "bytedeck.com" ]; then
    LABEL="production"
else
    LABEL="staging"
fi

echo ""
echo "GitHub Actions deploy runner is not set up on this host."
echo "  install dir : $RUNNER_DIR"
echo "  repo        : $REPO_URL"
echo "  label       : $LABEL   (derived from ROOT_DOMAIN=${ROOT_DOMAIN:-<unset>})"
echo "  service user: $(whoami)"
printf "Set it up now? [y/N] "
read -r REPLY
case "$REPLY" in
    y|Y|yes|YES) ;;
    *) echo "Skipping runner setup."; exit 0 ;;
esac

echo ""
echo "Get a registration token (expires after ~1 hour):"
echo "  $REPO_URL/settings/actions/runners/new -> copy the value after --token"
printf "Registration token: "
read -r TOKEN
[ -n "$TOKEN" ] || { echo "No token given; aborting runner setup." >&2; exit 1; }

# Latest runner release (it self-updates afterwards, so 'latest at install
# time' is the right choice; no version to maintain here).
echo "Resolving latest runner version..."
VER="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest \
        | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p')"
[ -n "$VER" ] || { echo "Could not resolve the runner version from the GitHub API; set it up manually (see SERVER-README.md)." >&2; exit 1; }

echo "Installing actions-runner v$VER into $RUNNER_DIR..."
mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"
curl -fsSL -o runner.tar.gz \
    "https://github.com/actions/runner/releases/download/v${VER}/actions-runner-linux-x64-${VER}.tar.gz"
tar xzf runner.tar.gz && rm runner.tar.gz

# --unattended: no further prompts; --replace: take over a same-named runner.
./config.sh --unattended --replace \
    --url "$REPO_URL" \
    --token "$TOKEN" \
    --name "bytedeck-$LABEL" \
    --labels "$LABEL" \
    --work _work

# Install as a systemd service running as this user, so it survives reboots.
svc install "$(whoami)"
svc start

echo "$SETUP_VERSION" > "$MARKER"
echo ""
echo "Deploy runner installed and running (label: $LABEL)."
echo "Verify it shows as 'Idle' at: $REPO_URL/settings/actions/runners"
