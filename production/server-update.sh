#!/bin/sh

docker compose -f docker-compose.yml -f docker-compose.prod.aws.yml build

# Update the web apps systemd unit file
sudo cp production/systemd/bytedeck.com.service /etc/systemd/system/bytedeck.com.service

# Install override to force nginx server to relaod its configuration after certbot renews the SSL certificate
sudo mkdir -p /etc/systemd/system/snap.certbot.renew.service.d
sudo cp production/systemd/snap.certbot.renew.service.override.conf /etc/systemd/system/snap.certbot.renew.service.d/snap.certbot.renew.service.override.conf

sudo systemctl daemon-reload

sudo systemctl enable bytedeck.com.service
sudo systemctl restart bytedeck.com

docker compose logs -f