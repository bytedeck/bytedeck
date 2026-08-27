#!/bin/sh
# Wait for a compose service to report healthy, and fail if it never does.
#
# Usage: production/wait-for-healthy.sh <service> [timeout_seconds]
#
# Called by server-update.sh after the containers are swapped, so a deploy that
# leaves the site on the maintenance page exits non-zero instead of reporting
# success. `docker compose up -d` returns once the containers are *created*,
# which says nothing about whether uwsgi ever bound :8000.
#
# Also useful by hand on the host to answer "is the app actually up?":
#
#   ./production/wait-for-healthy.sh web 60
#
# The signal is the service's own healthcheck from docker-compose.yml, rather
# than a probe repeated here, so there is one definition of what healthy means.
# For `web` that healthcheck is a TCP connect to :8000, which is exactly the
# thing that silently fails: uwsgi runs with `need-app = true`, so it refuses to
# bind at all when the Django app cannot be imported.
#
# Waiting costs deploy wall-clock, not user-visible downtime: the site is
# serving from the moment uwsgi binds, and this only delays the job reporting
# done. Docker evaluates a healthcheck on its `interval` (30s for web), so even
# a container that came up instantly can take that long to be *reported*
# healthy.
set -e

service=${1:?usage: wait-for-healthy.sh <service> [timeout_seconds]}
timeout=${2:-600}

# How often to ask. Overridable so the tests can drive the loop quickly.
interval=${HEALTH_POLL_INTERVAL:-5}

# Always operate from the repo root, regardless of the caller's CWD.
cd "$(dirname "$0")/.."

# Inherited from server-update.sh when called from a deploy; the default is the
# same production file pair, so this also runs standalone on the host.
COMPOSE=${COMPOSE:-"docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml"}

# Report why the wait failed, then show what the service said about itself. A
# deploy that goes red is only useful if the log that explains it is in the job.
give_up() {
    echo "FAIL: $service $1 after ${waited}s" >&2
    echo "--- last 50 log lines from $service ---" >&2
    $COMPOSE logs --tail=50 --no-color "$service" >&2 2>/dev/null || true
    exit 1
}

waited=0
while :; do
    # One inspect for both facts, so a poll is a single round trip. `none` for
    # health covers a service with no healthcheck declared, where the container
    # running is the strongest signal available.
    container=$($COMPOSE ps -q "$service" 2>/dev/null | head -n 1)
    if [ -n "$container" ]; then
        report=$(docker inspect \
            -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' \
            "$container" 2>/dev/null || echo "unknown unknown")
        state=${report% *}
        health=${report#* }

        case "$state $health" in
            *" healthy")
                echo "OK: $service is healthy after ${waited}s"
                exit 0
                ;;
            "running none")
                echo "OK: $service is running after ${waited}s (no healthcheck declared)"
                exit 0
                ;;
            *" unhealthy")
                # Docker reports `starting`, not `unhealthy`, for the whole
                # start_period, so reaching unhealthy means the check has
                # really failed its retries. Nothing is gained by waiting out
                # the rest of the timeout.
                give_up "is unhealthy"
                ;;
            "exited "*|"dead "*)
                # `restart: unless-stopped` means a crash normally shows up as
                # `restarting`, which is worth waiting on. A container that has
                # settled into exited or dead is not coming back by itself.
                give_up "has $state"
                ;;
        esac
    fi

    if [ "$waited" -ge "$timeout" ]; then
        give_up "never became healthy"
    fi
    sleep "$interval"
    waited=$((waited + interval))
done
