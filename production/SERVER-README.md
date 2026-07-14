# Production & Staging Server Notes

This document describes how ByteDeck is deployed and operated. It reflects the
actual setup as of this writing; keep it updated when the infrastructure
changes.

## Overview

ByteDeck runs on **AWS**. Each environment (production and staging) is a single
**EC2** instance running the app, Celery, and nginx as Docker containers, with
**Postgres on RDS**, **static & media on S3 (served via CloudFront)**, and Redis
as the Celery broker / cache.

| Concern            | Production                          | Staging                              |
| ------------------ | ----------------------------------- | ------------------------------------ |
| Domain             | `bytedeck.com`, `*.bytedeck.com`    | `bytedeck-staging.com`, `*....`      |
| Host               | dedicated EC2 instance              | separate dedicated EC2 instance      |
| Deploy branch      | `master`                            | `staging`                            |
| Database           | AWS RDS (Postgres)                  | AWS RDS (Postgres)                   |
| Static & media     | S3 + CloudFront (`USE_S3=1`)        | S3 + CloudFront (`USE_S3=1`)         |
| Redis              | see [Redis](#redis)                 | see [Redis](#redis)                  |
| `DEBUG`            | `False`                             | `False`                              |

Staging mirrors production as closely as possible (same Docker images, same
nginx config, same `DEBUG=False` security settings) so it is a faithful
pre-production check.

### Branch / release flow

`develop` (the day-to-day integration branch) → `staging` (deploys to
`bytedeck-staging.com`) → `master` (deploys to production). Work is verified on
staging, then `staging` is merged into `master` and production is deployed.
Hotfixes may go straight to `staging`/`master`.

## Host layout

Each EC2 host runs Ubuntu with the app checked out at `/home/ubuntu/bytedeck`,
owned by the `ubuntu` user (uid/gid `1000`, member of the `docker` group). The
`WUID`/`WGID` environment variables (see the systemd unit) pass that uid/gid
into the containers so files written to mounted volumes (e.g. collected static)
are owned by `ubuntu` and not `root`.

## Containers (docker compose)

Production and staging both run:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml up -d
```

`docker-compose.override.yml` is **development only** (it defines the local
`db`, `redis`, and `pgadmin` containers and runs `runserver`). It is *not* used
in production, which is why prod points at RDS/managed services instead.

Services started in production:

| Service       | What it does                                                                 |
| ------------- | --------------------------------------------------------------------------- |
| `web`         | Django served by **uwsgi** (`uwsgi --ini uwsgi.aws.ini`), listening on `:8000`. On start it runs `migrate_schemas --shared`, `migrate_schemas --executor=multiprocessing`, and `collectstatic`. |
| `celery`      | Celery worker (`-c 3 -Q default`) for background tasks.                      |
| `celery-beat` | Celery beat scheduler (`DatabaseScheduler`) for periodic tasks.             |
| `nginx`       | Reverse proxy / TLS terminator, built from `./nginx`. Mounts `/etc/letsencrypt`. Publishes host `443 -> 8088` and `80 -> 8080` (the container listens on high ports because it runs as a non-root user). |

Postgres (RDS) and Redis are **not** compose services in production — they are
reached over the network via the `POSTGRES_*` / `REDIS_*` settings in `.env`.

## Deployment runbook

Deployment is **manual** (SSH to the host). There is currently no
auto-deploy on push — see [Automating deploys](#automating-deploys-future) for
how we could add it.

```bash
# On the EC2 host, as the ubuntu user:
cd /home/ubuntu/bytedeck
git pull                      # master (prod) or staging (staging host)
./production/server-update.sh
```

`production/server-update.sh` does the following:

1. `docker compose ... build` the images.
2. Copy `production/systemd/bytedeck.com.service` into `/etc/systemd/system/`.
3. Install the certbot-renew override (see [TLS](#tls--certificates)).
4. `systemctl daemon-reload`, then enable and **restart** `bytedeck.com.service`
   (which runs `docker compose ... up -d`).
5. `nginx -s reload` inside the nginx container (works around nginx sometimes
   not reconnecting to uwsgi after a restart).
6. Tail the compose logs.

The app is managed by the **`bytedeck.com.service`** systemd unit
(`Type=oneshot`, `RemainAfterExit=yes`) so it comes back up automatically on
host reboot. It sets `WUID=1000`/`WGID=1000` and runs the compose `up -d`.

> Note: the unit file is named `bytedeck.com.service` on both hosts. On the
> staging host it deploys the `staging` branch with a staging `.env`.

## TLS / certificates

Certificates are **Let's Encrypt wildcard certs** (`bytedeck.com` +
`*.bytedeck.com`, needed because every tenant deck is a subdomain), obtained via
the **certbot snap** using the **dns-route53** plugin (DNS-01 challenge, since
wildcards require it).

- Auto-renewal is handled by the certbot snap's systemd timer
  (`snap.certbot.renew.timer`, runs ~twice daily).
- Renewal alone doesn't make new certs available to the containerized nginx, so
  `production/systemd/snap.certbot.renew.service.override.conf` adds two
  `ExecStartPost` hooks: `chown -R ubuntu:ubuntu /etc/letsencrypt/` and an
  `nginx -s reload` inside the nginx container.
- nginx mounts `/etc/letsencrypt` from the host read-only via
  `docker-compose.prod.aws.yml`.

Verify the timer/override with:

```bash
systemctl status snap.certbot.renew.timer
systemctl status snap.certbot.renew.service
cat /etc/systemd/system/snap.certbot.renew.service.d/snap.certbot.renew.service.override.conf
```

nginx TLS config (`nginx/bytedeck.aws.conf`): TLS 1.2/1.3, Mozilla-intermediate
ciphers, OCSP stapling, HSTS, gzip. It denies illegal `Host` headers (returns
`444`) and drops connections to unknown server names.

## Static & media

`USE_S3=1` in production, so django-storages writes **static** and **media** to
**S3** and they are served through **CloudFront**. nginx does not serve app
media in normal operation.

> Legacy detail: `nginx/bytedeck.aws.conf` still contains a hardcoded
> `location ~ /media/(.*)$` that 301-redirects to a specific CloudFront
> distribution (`d10ge8y4vx8iud.cloudfront.net/public_media/$1`). It's a
> workaround for old hardcoded `/media/...` URLs and causes a redundant redirect
> hop. Prefer generating correct absolute S3/CloudFront URLs in the app and
> removing this block when practical.

## Database

Postgres runs on **AWS RDS**. `POSTGRES_HOST` in the production `.env` points at
the RDS endpoint; `POSTGRES_PASSWORD` must be set (unlike development, which uses
`POSTGRES_HOST_AUTH_METHOD=trust`).

**Backups:** automated **RDS snapshots**. Because media lives on S3 (versionable)
and the DB is on RDS, the EC2 host itself is largely disposable — it can be
rebuilt from the repo + `.env`.

Multi-tenant migration reminder: never run plain `migrate`. The `web` container
runs `migrate_schemas` on startup; to run migrations manually use
`migrate_schemas` (and `tenant_command` for management commands).

## Redis

Redis is the Celery **broker** (db `0`) and the Django **cache** (dbs `1`/`2`),
addressed via `REDIS_HOST` / `REDIS_PORT` in `.env`.

Currently Redis is on **AWS ElastiCache**. ElastiCache is comparatively
expensive for this workload; running a **Redis container on the EC2 host** is a
safe and much cheaper alternative if it is locked down. If migrating to a
self-hosted container:

- **Never expose it publicly.** Keep it on the compose `backend-network` and do
  not publish its port to the host's public interface (bind to the internal
  network or `127.0.0.1` only). Set a `requirepass` password as defense in
  depth.
- **Bound its memory** with `maxmemory` so it can't OOM the box. Since the same
  instance serves the broker *and* the cache, use `maxmemory-policy noeviction`
  (evicting broker/beat keys under an LRU policy would silently drop queued
  tasks); size `maxmemory` with headroom and monitor.
- **Apply host tuning.** `production/systemd/redis-host-setup.service` already
  exists for exactly this: it disables Transparent Huge Pages and sets
  `vm.overcommit_memory=1` (both recommended by Redis for a containerized
  server). Enable it (`systemctl enable --now redis-host-setup`) when running
  Redis on the host.
- **Add `restart: unless-stopped`** to the service so it recovers on crash.
- Persistence (RDB/AOF) is optional here — a lost broker queue on restart is
  usually acceptable for periodic tasks, and the cache is disposable.

## Host tuning

`production/systemd/redis-host-setup.service` (oneshot) disables THP and sets
`vm.overcommit_memory=1`. It is only relevant when Redis runs as a container on
the host (see above); it is a no-op benefit for ElastiCache.

## Environment variables

Configuration is entirely env-driven through `.env` on each host (read by
django-environ). `.env.example.aws` is the production/staging template — copy it
and fill in real values. Key production settings:

| Variable                         | Notes                                                            |
| -------------------------------- | --------------------------------------------------------------- |
| `DEBUG`                          | **Must be `False`** in prod/staging.                            |
| `SECRET_KEY`                     | Unique, 50+ random chars. Never the `Change.Me!` default.       |
| `ROOT_DOMAIN`                    | `bytedeck.com` (prod) / `bytedeck-staging.com` (staging). Drives `ALLOWED_HOSTS` (`.` + `ROOT_DOMAIN`) and the public-tenant Site. |
| `CSRF_TRUSTED_ORIGINS`           | Required in prod, e.g. `https://*.bytedeck.com`.                |
| `POSTGRES_HOST` / `_PORT` / `_DB_NAME` / `_USER` / `_PASSWORD` | RDS endpoint + credentials.       |
| `REDIS_HOST` / `REDIS_PORT`      | ElastiCache endpoint, or the Redis container/host if self-hosted.|
| `USE_S3`                         | `1` in prod/staging.                                            |
| `AWS_ACCESS_KEY_ID` / `_SECRET_ACCESS_KEY` | Leave blank to use the EC2 instance's IAM role (preferred); or set for a specific IAM user. |
| `AWS_STORAGE_BUCKET_NAME`, `CDN_static` | S3 bucket + CloudFront domain.                          |
| `WUID` / `WGID`                  | Host user's uid/gid (`1000`) so container-written files aren't root-owned. |
| Email (`EMAIL_HOST*`, `DEFAULT_FROM_EMAIL`, `ADMINS`, `SERVER_EMAIL`) | SMTP + error-report recipients. |

The `.env` files hold real secrets and are **not** in git (`.gitignore` excludes
`.env`). Keep a secure copy (e.g. a password manager / secrets store) so a host
can be rebuilt.

## Security settings

`settings.py` applies a production/staging hardening block whenever
`DEBUG=False` (secure cookies, HSTS with `includeSubDomains`, nosniff, referrer
policy, `SECURE_PROXY_SSL_HEADER`). `manage.py check --deploy` is run in CI
against the `DEBUG=False` path to prevent regressions.

nginx **must** forward the request scheme to uwsgi — `nginx/bytedeck.aws.conf`
sets `uwsgi_param HTTP_X_FORWARDED_PROTO $scheme;` in the `location /` block,
which pairs with `SECURE_PROXY_SSL_HEADER` in settings. This is required for
correct behaviour, not just for redirects: without it `request.is_secure()` is
always `False` behind the proxy, so `build_absolute_uri()` emits `http://` links
(password-reset emails, OAuth callbacks, pagination) even though the site is
HTTPS-only.

`SECURE_SSL_REDIRECT` is a separate, optional layer, left **off** by default
because nginx already redirects HTTP→HTTPS at the edge. To also enforce it inside
Django, set `SECURE_SSL_REDIRECT=True` in the env — but only with the
`HTTP_X_FORWARDED_PROTO` param above in place. Enabling it *without* the
forwarded scheme causes an infinite redirect loop (Django never sees a secure
request, so it redirects every request forever).

## Troubleshooting

- **502 / nginx not reaching the app after a deploy:** nginx sometimes doesn't
  reconnect to uwsgi after `web` restarts. Re-run the reload:
  `docker compose ... exec nginx nginx -s reload` (server-update.sh already does
  this).
- **Which user is each container running as:**
  `docker inspect $(docker ps -aq) --format '{{.Config.User}} {{.Name}}'`
- **Logs:** `docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml logs -f`
- **Redis warnings about THP / overcommit:** enable `redis-host-setup.service`.

## Automating deploys (future)

There is currently no automation on push to `master`/`staging`; deploys are
manual. Options to automate, roughly in order of preference:

1. **Self-hosted GitHub Actions runner on each EC2 host** — a workflow triggered
   on push to `master` (prod runner) / `staging` (staging runner) runs
   `git pull && ./production/server-update.sh`. No inbound SSH exposure; the
   runner pulls jobs from GitHub.
2. **GitHub Actions + SSH deploy** — a workflow SSHes into the host (dedicated
   deploy key stored as a repo/environment secret) and runs the deploy script.
   Simpler, but exposes an SSH path and needs the host key pinned.

Either should gate on CI passing first, and staging should auto-deploy before
production. Ask in an issue before implementing so we can decide on secrets and
runner placement.
