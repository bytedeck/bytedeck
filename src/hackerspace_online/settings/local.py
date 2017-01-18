

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
SECRET_KEY = '8(@^b-s07o7a(*durcp#sx!-8=cnq2-shiq61!7nznn=h$az7n'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = []

EMAIL_HOST = 'smtp.gmail.com'
EMAIL_HOST_USER = 'timberline.hackerspace@gmail.com'
EMAIL_HOST_PASSWORD =""
EMAIL_PORT = 587
EMAIL_USE_TLS = True

# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
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
