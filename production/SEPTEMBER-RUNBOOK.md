# September Load-Spike Runbook

ByteDeck runs on a single EC2 host (all containers) in front of an RDS Postgres
database. Load is near-zero over summer; the **first week of school after Labour
Day** is the annual peak. This runbook captures the infrastructure review that
motivated it, the standing config, and the exact steps to scale up for the spike
and back down after.

> TL;DR: the box is RAM-constrained and has OOM-killed a uwsgi worker before.
> The plan is: **swap as a backstop (done)**, **bounded worker memory (config,
> below)**, a **vertical scale-up for ~2 weeks around Labour Day**, and
> **alarms** so you find out before it falls over.

---

## 1. Findings that drive this plan (July 2026 review)

Measured on the production host and RDS:

| Component | Observed | Implication |
|---|---|---|
| **EC2** | `c5a.large` (2 vCPU / 3.8 GiB), **swap was 0** | RAM is the binding constraint; CPU (fixed-perf, no burst cliff) is secondary. |
| **OOM history** | `dmesg`: OOM killer killed uwsgi twice, each worker **~1.6 GiB RSS** on a single request | A single request can balloon a worker to >1.5 GiB → with no swap the box OOMs. Root cause is in request code, not just capacity. |
| **RDS** | `max_connections=185`, `shared_buffers=432 MB` → ~2 GiB class (t3/t4g.small) | **Connections are not a *current* bottleneck** (≈30 of 185 when measured, so no PgBouncer today). That is a summer reading, not a September one: if the §5 `DatabaseConnections` alarm fires, re-measure demand and then add pooling (PgBouncer) or move to a larger class. A 2 GiB *burstable* RDS can also exhaust CPU credits under sustained load. |
| **Redis** | 1.5 MB used / 256 MB cap, `noeviction` | Fine at idle; with `noeviction`, reaching the cap makes redis reject every command that needs more memory, so celery publishes fail too and the broker stalls, not just the cache. |
| **Disk** | 30 GB, was 72% full, ~11 GB reclaimable docker images | Kept in check by log rotation + periodic `docker image prune`. |
| **Tenants** | 41 schemas | Every all-schema task / migration iterates 41 schemas. Moderate. |

CloudWatch had no data for the prior September (the current EC2/RDS instances
are newer than that spike), so sizing below is from the current footprint + the
OOM evidence rather than last year's peak. Re-measure during the spike (§6).

---

## 2. Standing configuration (already in the repo)

These apply year-round; no action needed at spike time beyond the scale-up in §4.

- **Swap backstop:** a 4 GiB swapfile with `vm.swappiness=10` (emergency paging,
  not routine). Turns "OOM-kill a worker" into "briefly slow." Verify with
  `free -h` (Swap should show `4.0Gi`). If a fresh host lacks it, recreate:
  ```bash
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf && sudo sysctl vm.swappiness=10
  ```
- **Bounded web workers** (`src/uwsgi.aws.ini`): `processes = 6`,
  `reload-on-rss = 384` (recycle a worker that grows past 384 MB, after its
  request). Sized for `c5a.large`.
- **Bounded Redis** (`docker-compose.prod.aws.yml`): `--maxmemory 512mb`
  (`REDIS_MAXMEMORY` to override).
- **Bounded container logs:** json-file rotation (`DOCKER_LOG_MAX_SIZE`/
  `DOCKER_LOG_MAX_FILE`, default 10m × 5 per service).
- **Worker scaling hook:** `UWSGI_EXTRA_ARGS` in `.env` is appended to the
  uwsgi command (later flags win), so the spike scale-up is an env change, not
  a file edit.

---

## 3. Two weeks before Labour Day: prep checklist

- [ ] Confirm swap is present (`free -h`) and disk has headroom (`df -h /`);
      if tight, `docker image prune -af && docker builder prune -af`. (Safe for
      rollback: bytedeck rolls back by checking out an earlier git SHA and
      re-running `server-update.sh`, which **rebuilds** the image from source:
      it does not depend on a retained old image, so pruning old images can't
      break a rollback.)
- [ ] Confirm the RDS instance class in the AWS console (RDS → Databases). If
      it's a `*.small` burstable, plan the §4 RDS bump and watch
      `CPUCreditBalance`.
- [ ] **Turn on CloudWatch Database Insights** for the RDS instance if it is off
      (RDS → the DB → Modify → Monitoring). It took over from the old Performance
      Insights console in July 2026. **Standard** mode keeps that same core
      experience and pricing (no charge at the 7-day retention default) and is
      enough to show the hot queries during the spike; Advanced mode adds
      execution plans and on-demand analysis for a per-instance fee, so pick it
      only if you actually want those.
- [ ] Create the **CloudWatch alarms** in §5.
- [ ] Do a **dry-run migration** on staging and time `migrate_schemas` across all
      41 schemas, so you know the deploy window. Use an **anonymized or synthetic
      dump** sized like production, never a raw production dump: the tenant
      schemas hold student PII, and restoring one into staging widens who can
      read it. If a real dump is genuinely unavoidable, scrub it first, limit
      access to whoever is running the test, and delete it once the timing is
      recorded. Deploys are a full restart (brief downtime), so avoid deploying
      during peak hours in week 1.
- [ ] Skim the memory-hog review (#2081) and land any request-path fixes before
      the spike.

---

## 4. Scale-up (do the day before, off-hours)

**EC2 (the big lever):** `c5a.large` (2/3.8) → **`c5a.xlarge` (4 vCPU / 8 GiB)**
which doubles RAM (room for more workers + the fat-request tail + celery/redis) and
2× CPU. `c5a.2xlarge` (8/16) if you want large margin. `c5a` is fixed-perf, so
no CPU-credit cliff.

1. Announce a short maintenance window.
2. AWS console → EC2 → the instance → **Instance state → Stop**.
3. **Actions → Instance settings → Change instance type** → `c5a.xlarge` → Apply.
4. **Start** the instance. (Elastic IP stays attached; if no EIP, the public IP
   changes, so update DNS. Confirm before relying on it.)
5. SSH in; the app auto-starts via the `bytedeck.com.service` systemd unit
   (`docker compose ... up -d`). An SSH session lands in `~` and the app lives in
   `~/bytedeck`, so change into the repo before any compose command:
   ```bash
   cd ~/bytedeck && docker compose ps
   ```
   then load the site.
6. Raise the worker ceiling for the bigger box: in `~/bytedeck/.env` set
   ```dotenv
   # Size to the instance -- these are NOT generic values. On c5a.xlarge (8 GiB)
   # ~8 workers leaves headroom for celery, redis (1gb below), the OS, and the
   # ~1.6 GiB single-request tail (see #2081) that still exists until it's fixed.
   # Rule: processes * peak-worker-RSS must leave that headroom. Raise only if
   # `free -h` under load shows room.
   UWSGI_EXTRA_ARGS=--processes 8
   REDIS_MAXMEMORY=1gb
   ```
   then `sudo systemctl restart bytedeck.com` and confirm the worker count under
   load (`cd ~/bytedeck && docker compose exec web ps aux | grep uwsgi`).

**RDS (if burstable / small):** RDS → the DB → **Modify** → larger class (e.g.
`t3.small` → `t3.medium`/`m5.large`), **Apply immediately** (brief failover).
Do this off-hours; it's reversible.

---

## 5. CloudWatch alarms to create (before the spike)

Two different principals are involved here, and read-only access is not enough
for either of them:

- **Creating the alarms** needs `cloudwatch:PutMetricAlarm`. The EC2 instance
  role currently can't even read CloudWatch from the host (`AccessDenied`), so
  either create them in the **console** as an operator who holds that
  permission, or grant `cloudwatch:PutMetricAlarm` to the role.
- **Publishing the host memory/disk metrics** below needs
  `cloudwatch:PutMetricData` on the **CloudWatch agent's** role (AWS's managed
  `CloudWatchAgentServerPolicy` covers it). Without that the agent runs and
  silently publishes nothing, so the alarms sit in `INSUFFICIENT_DATA` forever.

Suggested alarms:

- **RDS** `CPUUtilization` > 80% (5 min), `FreeableMemory` < 200 MB,
  `DatabaseConnections` > 150 (of 185), and (if burstable) `CPUCreditBalance`
  < 50.
- **EC2** `CPUUtilization` > 85% (5 min).
- EC2 **memory and disk are not in CloudWatch** without the agent. Given the
  OOM history, install the CloudWatch agent (or a lightweight exporter) for
  `mem_used_percent` > 85% and `disk_used_percent` > 85% so the next OOM pages
  you *before* it happens. (Sentry, issue #2005, would also surface the app
  errors.)
- **Redis has no CloudWatch metrics either**, now that it is a container on this
  host rather than ElastiCache. So there is no alarm to create for it yet, and
  the `used_memory` / `maxmemory` and `errorstat_OOM` checks in §6 are a manual
  stopgap: with `noeviction`, hitting the cap makes celery publishes fail, not
  just cache writes. The durable fix is a redis exporter feeding the same
  CloudWatch agent as the host metrics above, alarming at ~80% of the cap.

**Give every one of them a notification action.** An alarm with no action just
changes colour in a console nobody is watching, which defeats the whole reason
for creating it. Point them all at a single SNS topic, subscribe whoever is on
call for the spike (email is the minimum), and record the topic name and that
owner here once it exists. Then **test it**: temporarily set one alarm's
threshold to something it breaches right away, confirm the mail actually
arrives, and put the threshold back.

The app already emails `ADMINS` on celery task failures and unhandled 5xx.

---

## 6. During week 1: what to watch

Run on the host during peak:
```bash
cd ~/bytedeck   # the -f compose files below are referenced relatively, so run from the repo dir
                # (an SSH session lands in ~ by default; the app lives in ~/bytedeck -- see the systemd unit)
C="docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml"
watch -n5 'free -h; echo; docker stats --no-stream'
# Redis: memory-cap pressure (used vs max -- with noeviction, reaching the cap
# refuses memory-increasing writes, which stalls the broker).
# rejected_connections/evicted_keys do
# NOT track that (they're connection-limit / eviction, both 0 here), so watch
# the used/max ratio and the OOM error counter instead:
$C exec -T redis redis-cli info memory      | grep -E 'used_memory:|used_memory_human|maxmemory:|maxmemory_human'
$C exec -T redis redis-cli info errorstats  | grep -i oom   # errorstat_OOM appears once a write is refused (want: no output)
$C exec -T redis redis-cli -n 0 llen default   # broker backlog; a growing number = celery can't keep up
# Postgres live connections vs the 185 ceiling
$C exec -T web python src/manage.py shell <<'PY'
from django.db import connection
with connection.cursor() as c:
    c.execute("SELECT count(*), state FROM pg_stat_activity GROUP BY state"); print(c.fetchall())
PY
# Did anything get OOM-killed?
sudo dmesg -T | grep -iE 'out of memory|killed process' | tail
```
Signals and responses:
- **Swap climbing + OOM lines** → a worker is ballooning; find the request
  (nginx access log around the time), lower `UWSGI_EXTRA_ARGS` processes if
  needed, and prioritize the request-code fix.
- **Redis `used_memory` approaching `maxmemory`, or any `errorstat_OOM`** →
  memory-increasing writes are about to be (or are being) refused. Give the box
  room *first*: raise host RAM (§4) or drop a uwsgi/celery worker. Only then
  raise `REDIS_MAXMEMORY` and restart. Raising the redis cap on an unchanged box
  takes that memory straight from the workers, which trades a broker stall for
  an OOM kill (see §7).
- **Broker `llen default` growing** → celery is behind; raise worker concurrency
  (`-c` in `docker-compose.yml`) if RAM allows, or add a second worker.
- **RDS CPU pegged / credits draining** → bump the RDS class (§4).

Record the real peak numbers here for next year:
```text
Year ____  peak: RAM used ____  swap ____  RDS conns ____/185  RDS CPU ____%  redis used ____/____
```

---

## 7. Scale-down (≈2 weeks after Labour Day, once load settles)

1. In `.env`, revert `UWSGI_EXTRA_ARGS` (back to the in-file default) and
   restore `REDIS_MAXMEMORY=512mb` **before** downsizing: a 1 GB redis cap on
   the 3.8 GiB `c5a.large` starves uWSGI/celery and recreates the OOM.
   Lowering the cap needs no check of what redis is holding first: persistence
   is disabled (`--save ""`, `--appendonly no`) and the restart in step 2 is a
   full `down`/`up`, so redis comes back empty and the smaller cap applies to a
   nearly empty dataset. Queued tasks are wiped along with it, which this setup
   already accepts (broker and cache are both disposable), so do the restart
   off-peak when nothing important is mid-flight.
2. `sudo systemctl restart bytedeck.com`, confirm the site is healthy, and check
   that redis picked up the lower cap. Redis publishes no host port, so the
   check goes through the container:
   ```bash
   cd ~/bytedeck
   C="docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml"
   $C exec -T redis redis-cli info memory | grep maxmemory
   ```
3. EC2 → Stop → Change instance type back to `c5a.large` → Start (off-hours).
4. RDS → Modify back to the smaller class if you bumped it.
5. Update the "Year ____ peak" line in §6 for next year's sizing.

## Rollback

Every step above is reversible. If a scale-up misbehaves, reverse §4 (change the
instance type back and `systemctl restart bytedeck.com`). The swap and the
in-file worker/redis **defaults** (`processes 6`, `REDIS_MAXMEMORY=512mb`) are
safe to keep on the small box year-round, but the **spike overrides**
(`UWSGI_EXTRA_ARGS`, `REDIS_MAXMEMORY=1gb`) must be reverted before/at downsizing
(§7), or they'll starve the 3.8 GiB box. Image pruning doesn't affect rollback:
rollback re-checks-out a git SHA and rebuilds (§3).

---

## Related

- Root-cause: the ~1.6 GiB request (memory-hog review, #2081): the durable fix. Swap +
  bigger box only buy headroom.
- Issue #2005, Sentry/GlitchTip for error tracking during the spike.
- `production/SERVER-README.md`: general server + deploy docs.
