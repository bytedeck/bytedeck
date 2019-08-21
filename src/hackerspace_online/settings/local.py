

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
from .base import *

#root of project: ...../src
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# INSTALLED_APPS += (
#     # https://django-debug-toolbar.readthedocs.io/en/1.4/
#     'debug_toolbar',
# )


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
# This is a non-secret key.  A different key is used in the productions settings file.
SECRET_KEY = 'notverysecretkey...gimmebetteroneinproduction'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

INTERNAL_IPS = ['127.0.0.1', '0.0.0.0']

ALLOWED_HOSTS = []

EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = 'sentmail/' # change this to a proper location

POSTMAN_MAILER_APP = 'django.core.mail'
# EMAIL_HOST = 'smtp.gmail.com'
# EMAIL_HOST_USER = 'timberline.hackerspace@gmail.com'
# EMAIL_HOST_PASSWORD = ''
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# DEFAULT_FROM_EMAIL = "Timberline Hackerspace"

# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases
POSTGRES_HOST = os.environ.get('POSTGRES_HOST', '127.0.0.1')
POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')

DATABASES = {
    # 'default': {
    #     'ENGINE': 'django.db.backends.sqlite3',
    #     'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    # }
   'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'postgres',
        'USER': 'postgres',
        'HOST': POSTGRES_HOST,
        'PORT': POSTGRES_PORT
    }
}

# Static files (CSS, JavaScript, Images) ####################
# https://docs.djangoproject.com/en/1.8/howto/static-files/

# The absolute path to the directory where collectstatic will collect static files for deployment.
# Set in production settings for deployment
#STATIC_ROOT = os.path.join(BASE_DIR, "static_in_project",  "static_root")

STATICFILES_DIRS = (
    os.path.join(BASE_DIR, "static_in_project",  "static_root"),
    # '/var/www/static/',
)

MEDIA_URL = "/media/"
# The absolute path to the directory where collectstatic will collect static files for deployment.
# Set properly in production settings for deployment
MEDIA_ROOT = os.path.join(BASE_DIR, "static_in_project",  "media_root")


# END STATIC #######################################

# DEBUG TOOLBAR
MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware', ]
INSTALLED_APPS += ('debug_toolbar',
                   'template_timings_panel',
                   # http://django-cachalot.readthedocs.io
                   # 'cachalot',
                   )
DEBUG_TOOLBAR_PANELS = [
    'debug_toolbar.panels.versions.VersionsPanel',
    'debug_toolbar.panels.timer.TimerPanel',
    'debug_toolbar.panels.settings.SettingsPanel',
    'debug_toolbar.panels.headers.HeadersPanel',
    'debug_toolbar.panels.request.RequestPanel',
    'debug_toolbar.panels.sql.SQLPanel',
    'debug_toolbar.panels.staticfiles.StaticFilesPanel',
    'debug_toolbar.panels.templates.TemplatesPanel',
    'template_timings_panel.panels.TemplateTimings.TemplateTimings',
    # 'cachalot.panels.CachalotPanel',
    'debug_toolbar.panels.cache.CachePanel',
    'debug_toolbar.panels.signals.SignalsPanel',
    'debug_toolbar.panels.logging.LoggingPanel',
    'debug_toolbar.panels.redirects.RedirectsPanel',
]