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
| **EC2** | `c5a.large` — 2 vCPU / 3.8 GiB, **swap was 0** | RAM is the binding constraint; CPU (fixed-perf, no burst cliff) is secondary. |
| **OOM history** | `dmesg`: OOM killer killed uwsgi twice, each worker **~1.6 GiB RSS** on a single request | A single request can balloon a worker to >1.5 GiB → with no swap the box OOMs. Root cause is in request code, not just capacity. |
| **RDS** | `max_connections=185`, `shared_buffers=432 MB` → ~2 GiB class (t3/t4g.small) | **Connections are not a bottleneck** (≈30 used of 185; no PgBouncer needed). A 2 GiB *burstable* RDS can exhaust CPU credits under sustained load. |
| **Redis** | 1.5 MB used / 256 MB cap, `noeviction` | Fine at idle; with `noeviction`, hitting the cap refuses **all** writes and breaks the celery broker. |
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

## 3. Two weeks before Labour Day — prep checklist

- [ ] Confirm swap is present (`free -h`) and disk has headroom (`df -h /`);
      if tight, `docker image prune -af && docker builder prune -af`.
- [ ] Confirm the RDS instance class in the AWS console (RDS → Databases). If
      it's a `*.small` burstable, plan the §4 RDS bump and watch
      `CPUCreditBalance`.
- [ ] **Enable RDS Performance Insights** (free tier, 7-day retention) if off —
      it shows the exact hot queries during the spike.
- [ ] Create the **CloudWatch alarms** in §5.
- [ ] Do a **dry-run migration** on staging with a production-sized DB dump and
      time `migrate_schemas` across all 41 schemas, so you know the deploy
      window. Deploys are full-restart (brief downtime) — avoid deploying during
      peak hours in week 1.
- [ ] Skim the memory-hog review (linked in §7) and land any request-path fixes
      before the spike.

---

## 4. Scale-up (do the day before, off-hours)

**EC2 (the big lever):** `c5a.large` (2/3.8) → **`c5a.xlarge` (4 vCPU / 8 GiB)**
— doubles RAM (room for more workers + the fat-request tail + celery/redis) and
2× CPU. `c5a.2xlarge` (8/16) if you want large margin. `c5a` is fixed-perf, so
no CPU-credit cliff.

1. Announce a short maintenance window.
2. AWS console → EC2 → the instance → **Instance state → Stop**.
3. **Actions → Instance settings → Change instance type** → `c5a.xlarge` → Apply.
4. **Start** the instance. (Elastic IP stays attached; if no EIP, the public IP
   changes — update DNS. Confirm before relying on it.)
5. SSH in; the app auto-starts via the `bytedeck.com.service` systemd unit
   (`docker compose ... up -d`). Verify: `docker compose ps`, then load the site.
6. Raise the worker ceiling for the bigger box: in `~/bytedeck/.env` set
   ```
   UWSGI_EXTRA_ARGS=--processes 12
   REDIS_MAXMEMORY=1gb
   ```
   then `sudo systemctl restart bytedeck.com` and confirm 12 uwsgi workers
   under load (`docker compose exec web ps aux | grep uwsgi`).

**RDS (if burstable / small):** RDS → the DB → **Modify** → larger class (e.g.
`t3.small` → `t3.medium`/`m5.large`), **Apply immediately** (brief failover).
Do this off-hours; it's reversible.

---

## 5. CloudWatch alarms to create (before the spike)

The EC2 instance role can't read CloudWatch from the host (`AccessDenied`); set
these in the **console** (or attach a read-only policy to the role). Suggested:

- **RDS** `CPUUtilization` > 80% (5 min), `FreeableMemory` < 200 MB,
  `DatabaseConnections` > 150 (of 185), and — if burstable — `CPUCreditBalance`
  < 50.
- **EC2** `CPUUtilization` > 85% (5 min).
- EC2 **memory and disk are not in CloudWatch** without the agent. Given the
  OOM history, install the CloudWatch agent (or a lightweight exporter) for
  `mem_used_percent` > 85% and `disk_used_percent` > 85% so the next OOM pages
  you *before* it happens. (Sentry — issue #2005 — would also surface the app
  errors.)

The app already emails `ADMINS` on celery task failures and unhandled 5xx.

---

## 6. During week 1 — what to watch

Run on the host during peak:
```bash
C="docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml"
watch -n5 'free -h; echo; docker stats --no-stream'
# Redis: cap pressure + rejected writes (must stay 0)
$C exec -T redis redis-cli info memory  | grep -E 'used_memory_human|maxmemory_human'
$C exec -T redis redis-cli info stats   | grep -E 'rejected_connections|evicted_keys'
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
- **Redis `rejected_connections` > 0 or used ≈ max** → raise `REDIS_MAXMEMORY`
  (and give the box RAM) and restart.
- **Broker `llen default` growing** → celery is behind; raise worker concurrency
  (`-c` in `docker-compose.yml`) if RAM allows, or add a second worker.
- **RDS CPU pegged / credits draining** → bump the RDS class (§4).

Record the real peak numbers here for next year:
```
Year ____  peak: RAM used ____  swap ____  RDS conns ____/185  RDS CPU ____%  redis used ____/____
```

---

## 7. Scale-down (≈2 weeks after Labour Day, once load settles)

1. In `.env`, revert `UWSGI_EXTRA_ARGS` and `REDIS_MAXMEMORY` (or leave the
   redis bump if RAM allows).
2. `sudo systemctl restart bytedeck.com` and confirm the site is healthy.
3. EC2 → Stop → Change instance type back to `c5a.large` → Start (off-hours).
4. RDS → Modify back to the smaller class if you bumped it.
5. Update the "Year ____ peak" line in §6 for next year's sizing.

## Rollback

Every step above is reversible. If a scale-up misbehaves, reverse §4 (change the
instance type back and `systemctl restart bytedeck.com`). The swap, worker, and
redis-cap settings are safe to keep on the small box year-round.

---

## Related

- Root-cause: the ~1.6 GiB request (memory-hog review) — the durable fix; swap +
  bigger box only buy headroom.
- Issue #2005 — Sentry/GlitchTip for error tracking during the spike.
- `production/SERVER-README.md` — general server + deploy docs.
