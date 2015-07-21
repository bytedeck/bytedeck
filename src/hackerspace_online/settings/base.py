"""
Django settings for hackerspace_online project.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os

#root of project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

# Define secret key in local and production files
# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY = ''


# SECURITY WARNING: don't run with debug turned on in production!
#DEBUG set in local or production file
#DEBUG = True


ALLOWED_HOSTS = []

EMAIL_HOST = 'smtp.gmail.com'
EMAIL_HOST_USER = 'timberline.hackerspace@gmail.com'
EMAIL_HOST_PASSWORD =""
EMAIL_PORT = 587
EMAIL_USE_TLS = True

# Application definition

INSTALLED_APPS = (
    #default apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.sites', #for allauth
    'django.contrib.staticfiles',

    #third party apps

    # https://django-allauth.readthedocs.org/en/latest/installation.html
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    # 'allauth.socialaccount.providers.google',
    # 'allauth.socialaccount.providers.facebook',

    #http://django-crispy-forms.readthedocs.org/en/latest/install.html
    'crispy_forms',

    # https://github.com/summernote/django-summernote
    'django_summernote',

    #http://haystacksearch.org/
    'haystack',

    #local apps
    'quest_manager',
    'profile_manager',
    'announcements',
)

MIDDLEWARE_CLASSES = (
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
)

ROOT_URLCONF = 'hackerspace_online.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',

                # "allauth" specific context processors
                'allauth.account.context_processors.account',
                'allauth.socialaccount.context_processors.socialaccount'
            ],
        },
    },
]

AUTHENTICATION_BACKENDS = (

    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',

    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend',

)

WSGI_APPLICATION = 'hackerspace_online.wsgi.application'


# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'db.sqlite3'),
    }
}


# Internationalization
# https://docs.djangoproject.com/en/1.8/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'America/Vancouver'

USE_I18N = True

USE_L10N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images) ####################
# https://docs.djangoproject.com/en/1.8/howto/static-files/
# Statics file settings are in the local and production files

CRISPY_TEMPLATE_PACK = 'bootstrap3'

# ID 1 was set to example.com whendb was initialized
SITE_ID = 2

# AllAuth Configuration
# https://django-allauth.readthedocs.org/en/latest/configuration.html
ACCOUNT_USERNAME_MIN_LENGTH = 4
LOGIN_REDIRECT_URL = '/'
# ACCOUNT_SIGNUP_FORM_CLASS (=None)
# ACCOUNT_FORMS ({
#     'signup': ''
#
# })

#Haystack Search app
HAYSTACK_CONNECTIONS = {
    'default': {
        'ENGINE': 'haystack.backends.elasticsearch_backend.ElasticsearchSearchEngine',
        'URL': 'http://127.0.0.1:9200/',
        'INDEX_NAME': 'haystack',
    },
}

SUMMERNOTE_CONFIG = {
    # Using SummernoteWidget - iframe mode
    'iframe': True,  # or set False to use SummernoteInplaceWidget - no iframe mode
    #need iframe for embedding youtube

    # Using Summernote Air-mode
    'airMode': False,

    # Use native HTML tags (`<b>`, `<i>`, ...) instead of style attributes
    # (Firefox, Chrome only)
    # 'styleWithTags': True,

    # Set text direction : 'left to right' is default.
    'direction': 'ltr',

    # Change editor size
    'width': '700',
    'height': '480',

    # Use proper language setting automatically (default)
    'lang': None,

    # Or, set editor language/locale forcely
    # 'lang': 'ko-KR',

    # Customize toolbar buttons
    # 'toolbar': [
    #     ['style', ['style']],
    #     ['style', ['bold', 'italic', 'underline', 'clear']],
    #     ['para', ['ul', 'ol', 'height']],
    #     ['insert', ['link']],
    # ],

    # Need authentication while uploading attachments.
    'attachment_require_authentication': True,

    # Set `upload_to` function for attachments.
    #'attachment_upload_to': my_custom_upload_to_func(),

    # Set custom storage class for attachments.
    #'attachment_storage_class': 'my.custom.storage.class.name',

    # Set external media files for SummernoteInplaceWidget.
    # !!! Be sure to put {{ form.media }} in template before initiate summernote.
    'inplacewidget_external_css': (
        '//netdna.bootstrapcdn.com/bootstrap/3.1.1/css/bootstrap.min.css',
        '//netdna.bootstrapcdn.com/font-awesome/4.0.3/css/font-awesome.min.css',
    ),
    'inplacewidget_external_js': (
        '//code.jquery.com/jquery-1.9.1.min.js',
        '//netdna.bootstrapcdn.com/bootstrap/3.1.1/js/bootstrap.min.js',
    ),
}
