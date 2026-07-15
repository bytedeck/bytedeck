#!/bin/sh
# Build the images and (re)start the app via its systemd unit.
#
# Run from anywhere, either manually on the host or automatically by the Deploy
# workflow (.github/workflows/deploy.yml) on a self-hosted runner.
set -e

# Always operate from the repo root, regardless of the caller's CWD.
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml"

$COMPOSE build

# Update the web app's systemd unit file
sudo cp production/systemd/bytedeck.com.service /etc/systemd/system/bytedeck.com.service

# Install override to force nginx to reload its configuration after certbot renews the SSL certificate
sudo mkdir -p /etc/systemd/system/snap.certbot.renew.service.d
sudo cp production/systemd/snap.certbot.renew.service.override.conf /etc/systemd/system/snap.certbot.renew.service.d/snap.certbot.renew.service.override.conf

# Load the new systemd modules
sudo systemctl daemon-reload

# Ensure the service is enabled then restart it
sudo systemctl enable bytedeck.com.service
sudo systemctl restart bytedeck.com

# Restart the nginx server: sometimes nginx doesn't reconnect to uwsgi after a
# restart, and this helps when run manually. Best-effort: -T avoids needing a
# TTY (so it works on the runner), and a failed reload shouldn't fail the deploy.
$COMPOSE exec -T nginx nginx -s reload || echo "WARN: nginx reload failed; continuing."

# Show logs. Follow them when run interactively; in an automated deploy (no TTY,
# e.g. the CI runner) print a recent snapshot and exit so the job can finish.
if [ -t 1 ]; then
  $COMPOSE logs -f
else
  $COMPOSE logs --tail=100 --no-color
fi
