#!/bin/sh

docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml build

# Update the web apps systemd unit file
sudo cp production/systemd/bytedeck.com.service /etc/systemd/system/bytedeck.com.service

# Install override to force nginx server to relaod its configuration after certbot renews the SSL certificate
sudo mkdir -p /etc/systemd/system/snap.certbot.renew.service.d
sudo cp production/systemd/snap.certbot.renew.service.override.conf /etc/systemd/system/snap.certbot.renew.service.d/snap.certbot.renew.service.override.conf

# load the new systemd modules
sudo systemctl daemon-reload

# ensure the service is enabled then restart it
sudo systemctl enable bytedeck.com.service
sudo systemctl restart bytedeck.com

# Restart the nginx server
# sometime nginx doens't reconnect to uwsgi, this help when run manually
# hoping this fixes the problem
docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml exec nginx nginx -s reload


docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml logs -f