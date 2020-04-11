#!/bin/sh
cd /app/src
python manage.py migrate_schemas --shared
python manage.py collectstatic --no-input
