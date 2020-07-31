

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
import sys
from .base import *

# root of project: ...../src
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))



# TESTING = 'test' in sys.argv
# if TESTING:
#     # Use weaker password hasher for speeding up tests (when tested)
#     PASSWORD_HASHERS = [
#         'django.contrib.auth.hashers.MD5PasswordHasher',
#     ]

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/


EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = 'sentmail/'  # change this to a proper location

POSTMAN_MAILER_APP = 'django.core.mail'
# EMAIL_HOST = 'smtp.gmail.com'
# EMAIL_HOST_USER = 'timberline.hackerspace@gmail.com'
# EMAIL_HOST_PASSWORD = ''
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True
# DEFAULT_FROM_EMAIL = "Timberline Hackerspace"

# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases
# POSTGRES_HOST = os.environ.get('POSTGRES_HOST', '127.0.0.1')
# POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
#
# DATABASES = {
#     # 'default': {
#     #     'ENGINE': 'django.db.backends.sqlite3',
#     #     'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
#     # }
#    'default': {
#         'ENGINE': 'django.db.backends.postgresql',
#         'NAME': 'postgres',
#         'USER': 'postgres',
#         'PASSWORD': 'hellonepal',
#         'HOST': POSTGRES_HOST,
#         'PORT': POSTGRES_PORT
#     }
# }

# Static files (CSS, JavaScript, Images) ####################
# https://docs.djangoproject.com/en/1.8/howto/static-files/

# The absolute path to the directory where collectstatic will collect static files for deployment.
# Set in production settings for deployment
STATIC_ROOT = os.path.join(BASE_DIR, "static_in_project",  "local_static_root")

STATICFILES_DIRS = (
    os.path.join(BASE_DIR, "static_in_project", "static_root"),
    # '/var/www/static/',
)


# The absolute path to the directory where collectstatic will collect static files for deployment.
# Set properly in production settings for deployment
MEDIA_ROOT = os.path.join(BASE_DIR, "static_in_project", "media_root")


# END STATIC #######################################


# TENANT_DEFAULT_SUPERUSER_USERNAME = 'admin'
# TENANT_DEFAULT_SUPERUSER_PASSWORD = 'password'
