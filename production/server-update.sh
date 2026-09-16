#!/bin/sh
# Build the images, migrate, and swap the running containers for the new ones.
#
# Run from anywhere, either manually on the host or automatically by the Deploy
# workflow (.github/workflows/deploy.yml) on a self-hosted runner.
#
# Ordered so the slow work happens while the previous version is still serving:
# build, then migrate and collect static from the new image, and only then
# replace the containers. What a visitor can see is the last step.
set -e

# Always operate from the repo root, regardless of the caller's CWD.
cd "$(dirname "$0")/.."

# Exported so wait-for-healthy.sh below acts on the same stack rather than
# falling back to its own default.
COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml"
export COMPOSE

# Reclaim disk before building so image layers and BuildKit cache left by earlier
# deploys can't fill the host and fail the build mid-`pip install` ([Errno 28] No
# space left on device). Only unused data is removed: dangling images (a previous
# deploy's now-superseded image) and build cache. Named volumes (the Postgres
# data) are never touched. Best-effort: a prune hiccup shouldn't fail the deploy.
docker image prune -f || echo "WARN: docker image prune failed; continuing."
docker builder prune -f || echo "WARN: docker builder prune failed; continuing."

# Build on freshly pulled base images. --pull re-fetches each FROM image
# (python:3.12-slim for web/celery/celery-beat, nginx:stable for nginx) on every
# deploy, so the OS-level security updates published under those tags reach the
# containers: Docker builds on whatever copy of a tag is already on the host,
# however old it is, and these tags are updated in place upstream.
#
# The pull is best effort, like the prunes above. --pull makes the build require
# the registry, and it aborts rather than falling back when the registry cannot
# be reached, which would leave us unable to deploy (or to roll back, exactly
# when speed matters) during a registry outage. Retrying without it builds on the
# base already on the host, trading a possibly stale base for a deploy that still
# works offline. A build that fails for any other reason fails again on the
# retry, so real errors still stop the deploy.
$COMPOSE build --pull || {
  echo "WARN: build with --pull failed (registry unreachable?); retrying with the base images already on this host."
  $COMPOSE build
}

# Update the web app's systemd unit file
sudo cp production/systemd/bytedeck.com.service /etc/systemd/system/bytedeck.com.service

# Install override to force nginx to reload its configuration after certbot renews the SSL certificate
sudo mkdir -p /etc/systemd/system/snap.certbot.renew.service.d
sudo cp production/systemd/snap.certbot.renew.service.override.conf /etc/systemd/system/snap.certbot.renew.service.d/snap.certbot.renew.service.override.conf

# Install the Redis host tuning (disable THP, vm.overcommit_memory=1 -- the
# settings the dockerized Redis warns about at startup). Runs now and on boot.
sudo cp production/systemd/redis-host-setup.service /etc/systemd/system/redis-host-setup.service

# Ensure the GitHub Actions deploy runner is set up (idempotent: skips fast
# when already installed and running; offers interactive setup when missing
# and a human is at the terminal). Never fails the deploy.
./production/setup-runner.sh || echo "WARN: deploy-runner setup check failed; continuing."

# Load the new systemd modules
sudo systemctl daemon-reload

# Ensure the services are enabled and apply the Redis host tuning
sudo systemctl enable redis-host-setup.service
sudo systemctl restart redis-host-setup.service
sudo systemctl enable bytedeck.com.service

# Migrate and publish static files from the NEW image while the OLD containers
# are still serving. Both steps are slow -- migrate_schemas walks every tenant
# schema, and collectstatic uploads to S3 over the network -- and doing them
# here rather than inside the replacement web container is what keeps them out
# of the window when nginx has no backend to talk to.
#
# `run --rm --no-deps` starts a one-off container from the image built above,
# on the same networks, and leaves every running service alone: --no-deps so it
# cannot recreate redis underneath the containers currently using it, --rm so
# these do not pile up as exited containers. The database is RDS, reached over
# the network, so a one-off container talks to exactly the database the running
# app is using.
#
# A migration that fails now stops the deploy with the previous version still
# serving, instead of replacing it and leaving nginx on the maintenance page.
# The trade is that each migration has to be readable by the code it replaces
# for the seconds between here and the switch below: Django selects every
# concrete field of a model, so a column the outgoing version still declares
# and no longer finds raises ProgrammingError on ordinary reads. Dropping one
# safely takes two releases; see CONTRIBUTING.md, "Migrations and the deploy
# window".
$COMPOSE run --rm --no-deps web python src/manage.py migrate_schemas --shared
$COMPOSE run --rm --no-deps web python src/manage.py migrate_schemas --executor=multiprocessing
$COMPOSE run --rm --no-deps web python src/manage.py collectstatic --noinput

# Swap the containers. `up -d` recreates only the services whose image or
# configuration changed, which on a typical deploy is the three app services.
# redis is untouched, so queued Celery tasks survive, and what a visitor sees
# is the few seconds between the old web stopping and the new one binding
# :8000, covered by nginx's maintenance page.
#
# nginx usually keeps running through that, but not always: the build above
# passes --pull, so when the upstream nginx:stable tag has moved, nginx's image
# changes too and it is recreated with the rest, unbinding 443 for about a
# second. That second is a connection error rather than the maintenance page,
# so this is not a seamless deploy; it is bounded, and it only happens when the
# base image actually moved, where the unit restart described next unbinds 443
# on every deploy.
#
# Restarting the systemd unit instead would run its ExecStop, `docker compose
# down`, which removes every container: nginx included, so for part of the
# window nothing is listening on 443 at all and a visitor gets a connection
# error rather than the "ByteDeck is updating" page; and redis included, which
# runs with persistence disabled, so any Celery task still queued is lost.
#
# `systemctl start` is a no-op while the unit is active (it is, on every deploy
# after the first) and runs this same `up -d` when it is not, so systemd still
# owns the stack and still brings it back after a host reboot.
sudo systemctl start bytedeck.com
$COMPOSE up -d --remove-orphans

# Assert the app actually came back, and fail the deploy if it did not. `up -d`
# above returns once the containers are *created*, which is a much weaker claim
# than "the deploy worked": a bad setting, a missing env var or an import error
# in the deployed commit leaves uwsgi refusing to bind (`need-app = true`) and
# nginx serving the maintenance page, and without this the script would go on
# to print its logs and exit 0, so the Deploy job would go green over a site
# that is down.
#
# Failing here does not roll anything back. It makes the failure loud, and
# wait-for-healthy.sh puts the web log in the job output so the red run is
# worth opening. Rolling back is issue #2346: a rollback means rebuilding from
# an older commit, which is not something to do automatically.
#
# Invoked via the interpreter, not ./, for the reason deploy.yml gives for
# invoking this script the same way: a lost exec bit in git would otherwise
# fail the deploy with "Permission denied" for a reason that has nothing to do
# with the deploy.
sh production/wait-for-healthy.sh web

# Show logs. Follow them when run interactively; in an automated deploy (no TTY,
# e.g. the CI runner) print a recent snapshot and exit so the job can finish.
if [ -t 1 ]; then
  $COMPOSE logs -f
else
  $COMPOSE logs --tail=100 --no-color
fi
