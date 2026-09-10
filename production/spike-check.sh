#!/usr/bin/env bash
#
# One-shot load-bottleneck snapshot for the production/staging host.
#
#   cd ~/bytedeck && ./production/spike-check.sh              # snapshot now
#   cd ~/bytedeck && ./production/spike-check.sh --loop 60    # every 60s until Ctrl-C
#   cd ~/bytedeck && ./production/spike-check.sh --loop 60 | tee -a /tmp/spike.log
#
# Read-only: it starts nothing, restarts nothing and writes nothing outside
# stdout. Safe to run repeatedly at peak.
#
# Every section prints a VERDICT line naming what the number means and what to
# do about it, so nothing here needs a second document open to interpret. What
# the host cannot see for itself (CloudWatch, RDS Database Insights) is listed
# at the end with the exact place to look.
#
# See production/SEPTEMBER-RUNBOOK.md for the scale-up/scale-down procedures the
# verdicts refer to.

set -uo pipefail   # deliberately NOT -e: one failing probe must not abandon the rest

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml"
LOOP_SECONDS=""

while [ $# -gt 0 ]; do
    case "$1" in
        --loop) LOOP_SECONDS="${2:-60}"; shift 2 ;;
        -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

if [ ! -f docker-compose.prod.aws.yml ]; then
    echo "Run this from the repo root (cd ~/bytedeck), not $(pwd)." >&2
    exit 2
fi

section() { printf '\n\033[1;36m== %s %s\033[0m\n' "$1" "$(printf '=%.0s' $(seq 1 $((66 - ${#1}))))"; }
verdict() { printf '   \033[1;33m-> %s\033[0m\n' "$1"; }
note()    { printf '   %s\n' "$1"; }

snapshot() {
printf '\n\033[1m######## bytedeck spike-check  %s ########\033[0m\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')"

# ---------------------------------------------------------------- host RAM/CPU
section "HOST: memory, swap, load"
free -h
printf '\n'
uptime
SWAP_USED_MB=$(free -m | awk '/^Swap:/ {print $3}')
MEM_AVAIL_MB=$(free -m | awk '/^Mem:/ {print $7}')
if [ "${SWAP_USED_MB:-0}" -gt 200 ]; then
    verdict "SWAP IN USE (${SWAP_USED_MB}MB). Something is ballooning. See the OOM section below."
elif [ "${MEM_AVAIL_MB:-9999}" -lt 400 ]; then
    verdict "Available RAM is low (${MEM_AVAIL_MB}MB). Do NOT add uwsgi workers; scale the box (runbook section 4)."
else
    verdict "RAM has headroom (${MEM_AVAIL_MB}MB available). Adding workers is safe if listen_queue is backing up."
fi

# ------------------------------------------------------------------- OOM kills
section "OOM KILLS (the known failure mode, see issue #2081)"
OOM=$(sudo dmesg -T 2>/dev/null | grep -iE 'out of memory|killed process' | tail -5)
if [ -n "$OOM" ]; then
    echo "$OOM"
    verdict "A process was OOM-killed. Find the request in the nginx section, then lower --processes."
else
    note "none in dmesg"
    verdict "clean"
fi

# ----------------------------------------------------------------- disk
section "DISK"
df -h / | tail -1
DISK_PCT=$(df / | awk 'NR==2 {gsub("%",""); print $5}')
if [ "${DISK_PCT:-0}" -gt 85 ]; then
    verdict "Disk ${DISK_PCT}% full. Reclaim with: docker image prune -af && docker builder prune -af"
else
    verdict "ok (${DISK_PCT}% used)"
fi

# ------------------------------------------------------------ container usage
section "CONTAINERS (cpu / memory)"
docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}' 2>/dev/null \
    || note "docker stats unavailable"

# ------------------------------------------------------------- uwsgi saturation
section "UWSGI: worker saturation (the web-tier bottleneck signal)"
STATS=$($COMPOSE exec -T web curl -s --max-time 3 localhost:9191 2>/dev/null)
if [ -n "$STATS" ] && echo "$STATS" | grep -q listen_queue; then
    echo "$STATS" | python3 -c '
import json,sys
d = json.load(sys.stdin)
workers = d.get("workers", [])
busy = sum(1 for w in workers if w.get("status") == "busy")
print(f"  workers: {len(workers)}   busy: {busy}   listen_queue: {d.get(\"listen_queue\")} / {d.get(\"listen_queue_errors\")} errors")
slow = sorted(workers, key=lambda w: w.get("avg_rt", 0), reverse=True)[:3]
for w in slow:
    print(f"    worker {w.get(\"id\")}: avg_rt {w.get(\"avg_rt\",0)/1000:.0f}ms  requests {w.get(\"requests\")}  rss {w.get(\"rss\",0)//1048576}MB")
q = d.get("listen_queue", 0)
print("QUEUE" if q else "OK")
' 2>/dev/null | tee /tmp/.spike_uwsgi
    if grep -q QUEUE /tmp/.spike_uwsgi 2>/dev/null; then
        verdict "listen_queue > 0: requests are WAITING for a free worker. That is the bottleneck."
        verdict "  If RAM has headroom: raise --processes in UWSGI_EXTRA_ARGS, then systemctl restart bytedeck.com"
        verdict "  If RAM is tight: scale the instance instead (runbook section 4)."
    else
        verdict "No queue: workers are keeping up. If pages are slow, the cause is downstream (database)."
    fi
    rm -f /tmp/.spike_uwsgi
else
    note "uwsgi stats socket not enabled."
    verdict "TO ENABLE (needs one restart, do it BEFORE peak, not during):"
    verdict "  add to ~/bytedeck/.env:  UWSGI_EXTRA_ARGS=--stats 127.0.0.1:9191 --stats-http"
    verdict "  then: sudo systemctl restart bytedeck.com"
    note "Meanwhile, worker count only:"
    $COMPOSE exec -T web ps aux 2>/dev/null | grep -c '[u]wsgi' | sed 's/^/     uwsgi processes: /'
fi

# ------------------------------------------------------------- nginx: what is slow
section "NGINX: slowest requests and hottest decks"
LOGLINE=$($COMPOSE exec -T nginx sh -c 'tail -1 /var/log/nginx/access.log 2>/dev/null' 2>/dev/null)
if echo "$LOGLINE" | grep -q 'urt='; then
    note "Slowest ENDPOINTS by average app time (ids collapsed to #), count first:"
    $COMPOSE exec -T nginx sh -c '
        awk "{
            urt=\"\"; for(i=1;i<=NF;i++) if(\$i ~ /^urt=/){split(\$i,a,\"=\"); urt=a[2]}
            if(urt==\"\" || urt==\"-\") next
            if(match(\$0, /\"[A-Z]+ [^ ]+/)) {
                r=substr(\$0, RSTART+1, RLENGTH-1); split(r, m, \" \"); p=m[2]
                sub(/\?.*/, \"\", p); gsub(/[0-9]+/, \"#\", p)
                n[m[1]\" \"p]++; t[m[1]\" \"p]+=urt
            }
        } END { for(k in n) printf \"%7.3fs avg  x%-5d %s\n\", t[k]/n[k], n[k], k }" /var/log/nginx/access.log 2>/dev/null | sort -rn | head -10
    ' 2>/dev/null
    note ""
    note "Slowest INDIVIDUAL requests (the one-off 30s outliers):"
    $COMPOSE exec -T nginx sh -c '
        awk "{
            urt=\"\"; host=\"\"
            for(i=1;i<=NF;i++){
                if(\$i ~ /^urt=/){split(\$i,a,\"=\"); urt=a[2]}
                if(\$i ~ /^host=/){split(\$i,b,\"=\"); host=b[2]}
            }
            if(urt==\"\" || urt==\"-\") next
            if(match(\$0, /\"[A-Z]+ [^\"]*\"/)) printf \"%8.3fs  %-28s %s\n\", urt, host, substr(\$0, RSTART+1, RLENGTH-2)
        }" /var/log/nginx/access.log 2>/dev/null | sort -rn | head -8
    ' 2>/dev/null
    note ""
    note "Requests per deck (which tenant is carrying the load):"
    $COMPOSE exec -T nginx sh -c "
        grep -o 'host=[^ ]*' /var/log/nginx/access.log 2>/dev/null | sort | uniq -c | sort -rn | head -8
    " 2>/dev/null
    note ""
    note "Status codes:"
    $COMPOSE exec -T nginx sh -c "
        awk '{for(i=1;i<=NF;i++) if(\$i ~ /^[0-9][0-9][0-9]\$/) {print \$i; break}}' /var/log/nginx/access.log 2>/dev/null | sort | uniq -c | sort -rn | head -6
    " 2>/dev/null
    verdict "rt high but urt low  = slow client or big upload. Not your problem, ignore it."
    verdict "urt high on a few URLs = one slow endpoint. Take its query to RDS Database Insights."
    verdict "urt high everywhere    = the database is the bottleneck, not the web tier."
elif [ -n "$LOGLINE" ]; then
    note "Access log is on, but without timing fields, so slow requests cannot be ranked."
    verdict "Deploy the nginx.conf on this branch to get rt= and urt= and host=."
else
    note "NGINX ACCESS LOG IS OFF. You cannot tell which request is slow."
    verdict "THIS IS THE BIGGEST GAP. Deploy the nginx.conf change on this branch"
    verdict "  (production/server-update.sh), which turns it on with timing fields."
fi

# ------------------------------------------------------------------ redis
section "REDIS: broker and cache pressure"
$COMPOSE exec -T redis redis-cli info memory 2>/dev/null \
    | grep -E 'used_memory_human|maxmemory_human' | sed 's/^/   /'
REDIS_OOM=$($COMPOSE exec -T redis redis-cli info errorstats 2>/dev/null | grep -i oom)
QLEN=$($COMPOSE exec -T redis redis-cli -n 0 llen default 2>/dev/null | tr -d '\r')
note "celery queue depth (default): ${QLEN:-unreachable}"
if [ -z "$QLEN" ]; then
    verdict "Could not reach redis. If the container is down, celery and the cache are both dead: $COMPOSE ps"
elif [ -n "$REDIS_OOM" ]; then
    echo "   $REDIS_OOM"
    verdict "REDIS IS REFUSING WRITES. With noeviction this stalls the CELERY BROKER, not just the cache."
    verdict "  Give the box RAM FIRST (scale up), THEN raise REDIS_MAXMEMORY. Raising the cap alone causes an OOM kill."
elif [ "${QLEN:-0}" -gt 100 ]; then
    verdict "Celery is falling behind (${QLEN} queued). Raise worker concurrency (-c 3 in docker-compose.yml) if RAM allows."
else
    verdict "ok"
fi

# --------------------------------------------------------------- postgres/RDS
section "RDS: connections and slow in-flight queries"
$COMPOSE exec -T web python src/manage.py shell 2>/dev/null <<'PY'
from django.db import connection
with connection.cursor() as c:
    c.execute("SELECT count(*) FROM pg_stat_activity")
    total = c.fetchone()[0]
    c.execute("SHOW max_connections")
    cap = int(c.fetchone()[0])
    print(f"   connections: {total} / {cap}")
    if total > cap * 0.8:
        print(f"   -> CONNECTIONS NEARLY EXHAUSTED. Lower CONN_MAX_AGE or add PgBouncer.")
    c.execute("""
        SELECT round(extract(epoch from now()-query_start))::int AS secs, state, left(query, 110)
        FROM pg_stat_activity
        WHERE state <> 'idle' AND query_start IS NOT NULL AND pid <> pg_backend_pid()
        ORDER BY secs DESC LIMIT 8
    """)
    rows = c.fetchall()
    if rows:
        print("   longest running queries:")
        for secs, state, q in rows:
            print(f"     {secs:>4}s [{state}] {q}")
        if rows[0][0] and rows[0][0] > 5:
            print("   -> A QUERY HAS BEEN RUNNING >5s. This is very likely your bottleneck.")
            print("      Copy it into RDS Database Insights to see the plan, then index it.")
    else:
        print("   no queries in flight right now")
PY
[ $? -ne 0 ] && note "could not reach the database through the web container"

# ---------------------------------------------------- what this cannot see
section "CHECK THESE YOURSELF (not visible from this host)"
cat <<'MANUAL'
   These live in AWS and the script has no credentials for them. Open each one
   now, not after something breaks:

   1. RDS CPU + memory + connections
      AWS Console -> RDS -> Databases -> (the instance) -> Monitoring
      Watch: CPUUtilization > 80%, FreeableMemory < 200MB,
             DatabaseConnections climbing toward 185.
      If it is a *.small BURSTABLE class, also watch CPUCreditBalance: when
      credits hit zero the database is throttled and everything crawls.

   2. Which query is actually expensive
      AWS Console -> RDS -> the instance -> Database Insights (or Performance
      Insights) -> "Top SQL". This is the single most useful screen during a
      spike. If it is switched off, turn it on now (Modify -> Monitoring);
      Standard mode is free at 7-day retention.

   3. Slow query log (turn on now, it is DYNAMIC and needs no reboot)
      RDS -> Parameter groups -> your group -> log_min_duration_statement = 500
      Then RDS -> the instance -> Logs & events to read them.

   4. EC2 CPU
      AWS Console -> EC2 -> the instance -> Monitoring.
      Host RAM and disk are NOT in CloudWatch without the agent installed,
      which is why this script reads them locally instead.

   5. Application errors
      ADMINS email gets unhandled 5xx and celery task failures. Check that inbox.
MANUAL

printf '\n'
}

if [ -n "$LOOP_SECONDS" ]; then
    echo "Looping every ${LOOP_SECONDS}s. Ctrl-C to stop."
    while true; do snapshot; sleep "$LOOP_SECONDS"; done
else
    snapshot
fi
