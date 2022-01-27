#!/bin/sh

docker-compose -f docker-compose.yml -f docker-compose.prod.aws.yml build

sudo systemctl restart bytedeck.com

docker-compose logs -f