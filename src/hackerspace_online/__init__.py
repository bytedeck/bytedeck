# This will make sure the app is always imported when
# Django starts so that shared_task will use this app. # <-- not using shared_task anymore
# see https://github.com/maciej-gol/tenant-schemas-celery
from .celery import app as celery_app

__all__ = ('celery_app', 'default_app_config')

default_app_config = 'hackerspace_online.apps.HackerspaceConfig'
