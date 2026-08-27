#!/usr/bin/env bash
# Assert production/wait-for-healthy.sh passes and fails when it should.
#
# The deploy gate is only worth having if it goes red on a broken deploy and
# green on a working one, and both of those are states a live container reaches
# by accident at best. So `docker` is replaced on PATH with a stub that reports
# a scripted sequence of container states, which drives every branch of the
# wait loop directly: healthy, slow-then-healthy, unhealthy, exited, a missing
# container, and never becoming healthy at all.
#
# No Docker daemon and no images are needed, so this runs anywhere the rest of
# the checks do.
set -uo pipefail

cd "$(dirname "$0")/../.."

WORKDIR=$(mktemp -d)
trap 'rm -rf "$WORKDIR"' EXIT
STUB_DIR="$WORKDIR/bin"
mkdir -p "$STUB_DIR"

# The stub answers the two calls the gate makes. `compose ... ps -q` returns
# whatever CONTAINER_ID holds (empty stands in for "no such container"), and
# `inspect` pops the next line of STATE_SEQUENCE, repeating the last line once
# the sequence runs out so a poll loop can keep asking.
cat > "$STUB_DIR/docker" <<'STUB'
#!/usr/bin/env bash
for arg in "$@"; do
    case $arg in
        ps)      echo "${CONTAINER_ID-}"; exit 0 ;;
        logs)    echo "(stub log line)"; exit 0 ;;
        inspect) 
            line=$(head -n 1 "$STATE_SEQUENCE")
            if [ "$(wc -l < "$STATE_SEQUENCE")" -gt 1 ]; then
                tail -n +2 "$STATE_SEQUENCE" > "$STATE_SEQUENCE.next"
                mv "$STATE_SEQUENCE.next" "$STATE_SEQUENCE"
            fi
            echo "$line"
            exit 0 ;;
    esac
done
exit 0
STUB
chmod +x "$STUB_DIR/docker"

export PATH="$STUB_DIR:$PATH"
export HEALTH_POLL_INTERVAL=1

failures=0

# check <expected-exit: pass|fail> <description> <container-id> <state lines...>
check() {
    local expectation=$1 description=$2 container=$3
    shift 3
    export STATE_SEQUENCE="$WORKDIR/states"
    printf '%s\n' "$@" > "$STATE_SEQUENCE"
    export CONTAINER_ID="$container"

    local started elapsed status
    started=$(date +%s)
    if output=$(./production/wait-for-healthy.sh web 3 2>&1); then status=pass; else status=fail; fi
    elapsed=$(( $(date +%s) - started ))

    if [ "$status" = "$expectation" ]; then
        echo "  PASS  $description (exit $status in ${elapsed}s)"
    else
        echo "  FAIL  $description (expected $expectation, got $status)"
        echo "        output: $output"
        failures=$((failures + 1))
    fi
    LAST_ELAPSED=$elapsed
    LAST_OUTPUT=$output
}

echo "Driving the deploy health gate through its states..."

check pass "a container already healthy is accepted" abc123 "running healthy"

check pass "a container that starts slowly is waited for" abc123 \
    "running starting" "running starting" "running healthy"
if [ "$LAST_ELAPSED" -lt 1 ]; then
    echo "  FAIL  the slow-start case did not actually wait (${LAST_ELAPSED}s)"
    failures=$((failures + 1))
else
    echo "  PASS  the slow-start case actually waited (${LAST_ELAPSED}s)"
fi

check fail "an unhealthy container fails the deploy" abc123 "running unhealthy"
# The point of failing fast: an unhealthy verdict already survived the
# healthcheck's retries, so burning the remaining timeout tells nobody anything.
if [ "$LAST_ELAPSED" -lt 3 ]; then
    echo "  PASS  unhealthy fails fast rather than waiting out the timeout (${LAST_ELAPSED}s)"
else
    echo "  FAIL  unhealthy burned the whole timeout (${LAST_ELAPSED}s)"
    failures=$((failures + 1))
fi

check fail "an exited container fails the deploy" abc123 "exited none"
if [ "$LAST_ELAPSED" -lt 3 ]; then
    echo "  PASS  exited fails fast rather than waiting out the timeout (${LAST_ELAPSED}s)"
else
    echo "  FAIL  exited burned the whole timeout (${LAST_ELAPSED}s)"
    failures=$((failures + 1))
fi

check fail "a container that never becomes healthy fails the deploy" abc123 "running starting"
check fail "no container at all fails the deploy" "" "running healthy"

# A red deploy is only actionable if the job carries the reason and the log.
case "$LAST_OUTPUT" in
    *"FAIL:"*) echo "  PASS  failure output says why" ;;
    *) echo "  FAIL  failure output does not say why"; failures=$((failures + 1)) ;;
esac
case "$LAST_OUTPUT" in
    *"stub log line"*) echo "  PASS  failure output carries the service log" ;;
    *) echo "  FAIL  failure output carries no service log"; failures=$((failures + 1)) ;;
esac

# A container with no healthcheck declared: running is all there is to go on.
check pass "a running container with no healthcheck is accepted" abc123 "running none"

echo
echo "$failures failure(s)"
exit $(( failures > 0 ? 1 : 0 ))
