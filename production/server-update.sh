#!/bin/sh

docker-compose -f docker-compose.yml -f docker-compose.prod.aws.yml build

# Update the web apps systemd unit file
sudo cp production/systemd/bytedeck.com.service /etc/systemd/system/bytedeck.com.service
sudo systemctl daemon-reload

sudo systemctl restart bytedeck.com

docker-compose logs -f