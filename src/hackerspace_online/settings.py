"""
Django settings for hackerspace_online project.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os
import sys

# https://django-environ.readthedocs.io/en/latest/#django-environ
import environ

env = environ.Env(
    # set casting, default value
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list)
)


project_root = environ.Path(__file__) - 3  # "/"
PROJECT_ROOT = project_root()
BASE_DIR = project_root('src')  # "/src/"

# read in the .env file
environ.Env.read_env(os.path.join(project_root(), '.env'))

SECRET_KEY = env('SECRET_KEY')
DEBUG = env('DEBUG')
ROOT_DOMAIN = env('ROOT_DOMAIN', default='localhost')

ALLOWED_HOSTS = env('ALLOWED_HOSTS', default=[])
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = [f".{ROOT_DOMAIN}"]

WSGI_APPLICATION = 'hackerspace_online.wsgi.application'

# Application definition
SHARED_APPS = (
    'django_tenants',
    'tenant',
    'django.contrib.contenttypes',

    # WHY ARE THESE NEEDED IN BOTH SHARED AND TENANT APPS LISTS?
    # dylan was here :P delete me later
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.flatpages',
    ###########################################

    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    # tenant beat is not supported, have to do it manually with:
    # https://github.com/maciej-gol/tenant-schemas-celery#celery-beat-integration
    # or
    # https://github.com/maciej-gol/tenant-schemas-celery/issues/34
    # by inserting the schema into the task headers so that tenant-schams-celery knows where to run it
    'django_celery_beat',

    'django.contrib.sites',

    'captcha',

    'grappelli',
    'crispy_forms',
    'bootstrap_datepicker_plus',
    'embed_video',
    'django_select2',
    'url_or_relative_url_field',
    'import_export',
    'colorful',

)

TENANT_APPS = (
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.admin',
    'django.contrib.staticfiles',
    'django.contrib.flatpages',

    'allauth',
    'allauth.account',
    'allauth.socialaccount',

    # tenant beat is not supported, have to do it manually with:
    # https://github.com/maciej-gol/tenant-schemas-celery#celery-beat-integration
    # or
    # https://github.com/maciej-gol/tenant-schemas-celery/issues/34
    # by inserting the schema into the task headers so that tenant-schams-celery knows where to run it
    'django_celery_beat',

    'django.contrib.sites',  # required inside TENANT_APPS for allauth to work

    'hackerspace_online',

    # https://github.com/summernote/django-summernote
    'django_summernote',
    'bytedeck_summernote',

    'taggit',

    'quest_manager',
    'profile_manager',
    'announcements',
    'comments',
    'notifications',
    'courses',
    'prerequisites',
    'badges',
    'djcytoscape',
    'portfolios',
    'utilities',
    'siteconfig',
    'tags',
)


INSTALLED_APPS = (
    # http://django-grappelli.readthedocs.org/en/latest/quickstart.html
    'grappelli',

    'django_tenants',
    'tenant.apps.TenantConfig',

    # default apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.sites',  # for allauth
    'django.contrib.staticfiles',

    'django.contrib.flatpages',  # https://docs.djangoproject.com/en/1.10/ref/contrib/flatpages/

    # third party apps

    # https://django-allauth.readthedocs.org/en/latest/installation.html
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    # 'allauth.socialaccount.providers.facebook',

    # http://django-crispy-forms.readthedocs.org/en/latest/install.html
    'crispy_forms',

    # https://github.com/summernote/django-summernote
    'django_summernote',
    'bytedeck_summernote',

    # https://pypi.org/project/django-recaptcha/
    'captcha',

    # https://github.com/monim67/django-bootstrap-datepicker-plus
    'bootstrap_datepicker_plus',

    # https://github.com/yetty/django-embed-video
    # used for the EmbedVideoField that validates YouTube and Vimeo urls
    'embed_video',

    # https://github.com/applegrew/django-select2
    'django_select2',

    # https://github.com/timonweb/django-url-or-relative-url-field
    'url_or_relative_url_field',

    # https://django-import-export.readthedocs.io
    'import_export',

    'django_celery_beat',

    # https://github.com/charettes/django-colorful
    'colorful',

    # hackerspace_online.apps.HackerspaceConfig
    'hackerspace_online',

    # django storages
    'storages',

    # django-taggit: https://django-taggit.readthedocs.io/en/latest/index.html
    'taggit',

    # local apps
    'quest_manager',
    'profile_manager',
    'announcements',
    'comments',
    'notifications',
    'courses',
    'prerequisites',
    'badges',
    'djcytoscape',
    'portfolios',
    'utilities',
    'siteconfig',
    'tags',
)

TAGGIT_CASE_INSENSITIVE = True

MIDDLEWARE = [
    'django_tenants.middleware.TenantMiddleware',
    # caching: https://docs.djangoproject.com/en/1.10/topics/cache/
    # 'django.middleware.cache.UpdateCacheMiddleware',
    # 'django.middleware.cache.FetchFromCacheMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # used by django-date-time-widget
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
]

DB_LOGS_ENABLED = env('DB_LOGS_ENABLED', default=False)

if DB_LOGS_ENABLED:
    MIDDLEWARE.insert(0, 'hackerspace_online.middleware.ForceDebugCursorMiddleware')
    print(MIDDLEWARE)
    LOGS_PATH = os.path.join(os.sep, 'tmp', 'bytedeck')

    if not os.path.exists(LOGS_PATH):
        os.mkdir(LOGS_PATH)

    LOGGING = {
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '{levelname} | {asctime} | {process:d} {thread:d} | {message}',
                'style': '{',
            },
        },
        'handlers': {
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
            'file': {
                'level': 'DEBUG',
                'class': 'logging.handlers.TimedRotatingFileHandler',
                'when': 'M',  # Every minute (so that it would be much easier to view queries rather than by hour or day)
                'filename': os.path.join(LOGS_PATH, 'queries.log'),
                'formatter': 'verbose',
            }
        },
        'loggers': {
            'django.db.backends': {
                'handlers': ['file'],
                'level': 'DEBUG',
            },
        }
    }


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

                'hackerspace_online.context_processors.config',
            ],
            # 'string_if_invalid': 'DEBUG WARNING: undefined template variable [%s] not found',
        },
    },
]

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"


# REDIS AND CACHES #################################################

REDIS_HOST = env('REDIS_HOST', default='127.0.0.1')  # os.environ.get('REDIS_HOST', '127.0.0.1')
REDIS_PORT = env('REDIS_PORT')  # os.environ.get('REDIS_PORT', '6379')

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f"redis://{REDIS_HOST}:{REDIS_PORT}/1",
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_FUNCTION': 'django_tenants.cache.make_key',
        'REVERSE_KEY_FUNCTION': 'django_tenants.cache.reverse_key',
    },
    'select2': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': f'redis://{REDIS_HOST}:{REDIS_PORT}/2',
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        'KEY_FUNCTION': 'django_tenants.cache.make_key',
        'REVERSE_KEY_FUNCTION': 'django_tenants.cache.reverse_key',
        'TIMEOUT': None,
    }
}

SELECT2_CACHE_BACKEND = 'select2'


# I18N AND L10N ####################################################################

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'America/Vancouver'
USE_I18N = True
USE_L10N = True
USE_TZ = True


# CELERY ####################################################################

CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_MAX_RETRIES = 10
CELERY_TASKS_BUNCH_SIZE = 10

# allowed delay between conditions met updates for all users:
# In sec., wait before start next 'big' update for all conditions, if it's going to start - all other updates could be skipped
CONDITIONS_UPDATE_COUNTDOWN = 60 * 1


# DATABASES #######################################################

POSTGRES_HOST = env('POSTGRES_HOST', default='127.0.0.1')  # os.environ.get('POSTGRES_HOST', '127.0.0.1')
POSTGRES_PORT = env('POSTGRES_PORT')
POSTGRES_DB_NAME = env('POSTGRES_DB_NAME')
POSTGRES_USER = env('POSTGRES_USER')
POSTGRES_PASSWORD = env('POSTGRES_PASSWORD', default=None)

DATABASES = {
    'default': {
        'ENGINE': 'django_tenants.postgresql_backend',
        'NAME': POSTGRES_DB_NAME,
        'USER': POSTGRES_USER,
        'PASSWORD': POSTGRES_PASSWORD,
        'HOST': POSTGRES_HOST,
        'PORT': POSTGRES_PORT
    }
}

DATABASE_ROUTERS = (
    'django_tenants.routers.TenantSyncRouter',
)


# EMAIL ######################################

EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.filebased.EmailBackend')
EMAIL_FILE_PATH = env('EMAIL_BACKEND', default=os.path.join(PROJECT_ROOT, "_sent_mail"))

EMAIL_HOST = env('EMAIL_HOST', default=None)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default=None)
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default=None)

EMAIL_PORT = env('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env('EMAIL_USE_TLS', default=True)

DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=None)

# SERVER ERRORS EMAIL
admins_raw = env('ADMINS', default=[])
if admins_raw:
    # https://django-environ.readthedocs.io/en/latest/index.html?highlight=ADMINS#nested-lists
    ADMINS = [tuple(entry.split(':')) for entry in env.list('ADMINS')]
SERVER_EMAIL = env('SERVER_EMAIL', default=None)
EMAIL_SUBJECT_PREFIX = env('EMAIL_SUBJECT_PREFIX', default='[Bytedeck Dev] ')


# STATIC AND MEDIA ###########################

# Urls to display media and static, e.g. example.com/media/
MEDIA_URL = '/media/'
STATIC_URL = '/static/'

USE_S3 = env('USE_S3', default='0') == '1'
if USE_S3:

    # AWS settings
    AWS_ACCESS_KEY_ID = env('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = env('AWS_SECRET_ACCESS_KEY')

    # S3 settings
    AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_CUSTOM_DOMAIN = env('CDN_static')
    AWS_S3_OBJECT_PARAMETERS = {
        "ACL": "public-read",
        "CacheControl": "max-age=86400"
    }

    # S3 Static Files
    STATICFILES_LOCATION = 'static'
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{STATICFILES_LOCATION}/'
    STATICFILES_STORAGE = 'storage.custom_storages.StaticStorage'

    # Media Files

    # S3 public media files
    PUBLIC_MEDIAFILES_LOCATION = 'public_media'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{PUBLIC_MEDIAFILES_LOCATION}/'
    DEFAULT_FILE_STORAGE = 'storage.custom_storages.PublicMediaStorage'

    # S3 private media files
    # For any implementation in future, Refer https://testdriven.io/blog/storing-django-static-and-media-files-on-amazon-s3/
    PRIVATE_MEDIAFILES_LOCATION = 'private_media'
    PRIVATE_FILE_STORAGE = 'storage.custom_storages.PrivateMediaStorage'

else:

    # The absolute path to the directory where `collectstatic` will move the static files to.
    STATIC_ROOT = env('STATIC_ROOT', default=os.path.join(PROJECT_ROOT, "_collected_static"))

    # The absolute path to the directory where uploaded media files will be saved to
    MEDIA_ROOT = env('MEDIA_ROOT', default=os.path.join(PROJECT_ROOT, "_media_uploads"))


STATICFILES_DIRS = env(
    'STATICFILES_DIRS',
    default=(
        os.path.join(BASE_DIR, "static"),
        # '/var/www/static/',
    )
)

CRISPY_TEMPLATE_PACK = 'bootstrap3'

SITE_ID = 1

# https://github.com/charettes/django-colorful
GRAPPELLI_CLEAN_INPUT_TYPES = False


# PUBLIC TENANT ##############################

DEFAULT_SUPERUSER_USERNAME = env('DEFAULT_SUPERUSER_USERNAME')
DEFAULT_SUPERUSER_PASSWORD = env('DEFAULT_SUPERUSER_PASSWORD')
DEFAULT_SUPERUSER_EMAIL = env('DEFAULT_SUPERUSER_EMAIL', default='')


# TENANTS ###############################################################

TENANT_MODEL = "tenant.Tenant"
TENANT_DOMAIN_MODEL = "tenant.TenantDomain"

TENANT_DEFAULT_ADMIN_USERNAME = env('TENANT_DEFAULT_ADMIN_USERNAME')
TENANT_DEFAULT_ADMIN_PASSWORD = env('TENANT_DEFAULT_ADMIN_PASSWORD')
TENANT_DEFAULT_ADMIN_EMAIL = env('TENANT_DEFAULT_ADMIN_EMAIL', default='')

TENANT_DEFAULT_OWNER_USERNAME = env('TENANT_DEFAULT_OWNER_USERNAME')
TENANT_DEFAULT_OWNER_PASSWORD = env('TENANT_DEFAULT_OWNER_PASSWORD')
TENANT_DEFAULT_OWNER_EMAIL = env('TENANT_DEFAULT_OWNER_EMAIL', default='')

# See this: https://github.com/timberline-secondary/hackerspace/issues/388
# The design choice for media files it serving all the media files from one directory instead of separate directory for each tenant.
SILENCED_SYSTEM_CHECKS = ['django_tenants.W003']


# RECAPTCHA #######################################################

recaptcha_keys_available = env('RECAPTCHA_PRIVATE_KEY', default=None)
if recaptcha_keys_available:
    RECAPTCHA_PUBLIC_KEY = env('RECAPTCHA_PUBLIC_KEY')
    RECAPTCHA_PRIVATE_KEY = env('RECAPTCHA_PRIVATE_KEY')
else:
    # Google provides test keys which are set as the default for RECAPTCHA_PUBLIC_KEY and RECAPTCHA_PRIVATE_KEY.
    # These cannot be used in production since they always validate to true and a warning will be shown on the reCAPTCHA.
    pass


# Google provides default keys in development that always validate, but results in this error:
#  captcha.recaptcha_test_key_error: RECAPTCHA_PRIVATE_KEY or RECAPTCHA_PUBLIC_KEY is making
#  use of the Google test keys and will not behave as expected in a production environment
#
# Silencing the error allows us to setup an environment (otherwise the error will stop the app)
# The fact that we are not using production keys will be obvious on the recaptcha widget because a red warning message is displayed
SILENCED_SYSTEM_CHECKS += ['captcha.recaptcha_test_key_error']


# AUTHENTICATION ##################################################
SESSION_COOKIE_AGE = env("SESSION_COOKIE_AGE", default=int(60 * 60 * 24 * 7 * 8))  # 8 Weeks

AUTHENTICATION_BACKENDS = (

    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',

    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend',

)

# AllAuth Configuration
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'offline',
            # https://developers.google.com/identity/openid-connect/openid-connect#prompt
            'prompt': 'select_account',
        },
        'OAUTH_PKCE_ENABLED': True,
    }
}

# https://django-allauth.readthedocs.org/en/latest/configuration.html
LOGIN_REDIRECT_URL = '/'
# https://stackoverflow.com/questions/44571373/python-3-6-django1-10-login-required-decorator-redirects-to-link-with-missing/44571408#44571408
LOGIN_URL = 'account_login'
ACCOUNT_ADAPTER = "hackerspace_online.adapter.CustomAccountAdapter"
# Specifies the adapter class to use, allowing you to alter certain default behaviour.
ACCOUNT_AUTHENTICATION_METHOD = "username"  # (=”username” | “email” | “username_email”)
# Specifies the login method to use – whether the user logs in by entering their username,
# e-mail address, or either one of both. Setting this to “email” requires ACCOUNT_EMAIL_REQUIRED=True
# ACCOUNT_CONFIRM_EMAIL_ON_GET #(=False)
# Determines whether or not an e-mail address is automatically confirmed by a mere GET request.
# ACCOUNT_EMAIL_CONFIRMATION_ANONYMOUS_REDIRECT_URL #(=settings.LOGIN_URL)
# The URL to redirect to after a successful e-mail confirmation, in case no user is logged in.
ACCOUNT_EMAIL_CONFIRMATION_AUTHENTICATED_REDIRECT_URL = LOGIN_REDIRECT_URL  # (=None)
# The URL to redirect to after a successful e-mail confirmation, in case of an authenticated user. Set to None to use settings.LOGIN_REDIRECT_URL.
# ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS #(=3)
# Determines the expiration date of email confirmation mails (# of days).
# ACCOUNT_EMAIL_REQUIRED = True #(=False)
# The user is required to hand over an e-mail address when signing up.
ACCOUNT_EMAIL_VERIFICATION = "optional"
# Determines the e-mail verification method during signup – choose one of “mandatory”, “optional”, or “none”. When set to “mandatory”
# the user is blocked from logging in until the email address is verified. Choose “optional” or “none” to allow logins with an unverified
# e-mail address. In case of “optional”, the e-mail verification mail is still sent, whereas in case of “none” no e-mail verification mails are sent.
# ACCOUNT_EMAIL_SUBJECT_PREFIX #(=”[Site] ”)
# Subject-line prefix to use for email messages sent. By default, the name of the current Site (django.contrib.sites) is used.
ACCOUNT_DEFAULT_HTTP_PROTOCOL = os.getenv("ACCOUNT_DEFAULT_HTTP_PROTOCOL", "http" if DEBUG else "https")
# The default protocol used for when generating URLs, e.g. for the password forgotten procedure. Note that this is a default only –
# see the section on HTTPS for more information.
# ACCOUNT_FORMS #(={})
# Used to override forms, for example: {‘login’: ‘myapp.forms.LoginForm’}
ACCOUNT_FORMS = {
    'signup': 'hackerspace_online.forms.CustomSignupForm',
    'login': 'hackerspace_online.forms.CustomLoginForm',
}
# ACCOUNT_LOGOUT_ON_GET #(=False)
# Determines whether or not the user is automatically logged out by a mere GET request. See documentation for the LogoutView for details.
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True  # (=False)
# Determines whether or not the user is automatically logged out after changing the password. See documentation for Django’s session invalidation
#  on password change. (Django 1.7+)
ACCOUNT_LOGOUT_REDIRECT_URL = LOGIN_URL  # (=”/”)
ACCOUNT_PRESERVE_USERNAME_CASING = False
ACCOUNT_UNIQUE_EMAIL = True

# The maximum amount of email addresses a user can associate to his account.
# It is safe to change this setting for an already running project –
# it will not negatively affect users that already exceed the allowed amount.
# Note that if you set the maximum to 1, users will not be able to change their
# email address as they are unable to add the new address,
# followed by removing the old address.
# Uses the `allauth.account.models.EmailAddress`
ACCOUNT_MAX_EMAIL_ADDRESSES = 2


SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_FORMS = {
    'signup': 'hackerspace_online.forms.CustomSocialAccountSignupForm',
}
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_ADAPTER = "hackerspace_online.adapter.CustomSocialAccountAdapter"


#################################
#
# SUMMERNOTE WYSIWYG EDITOR
# https://github.com/summernote/django-summernote
#
#################################

SUMMERNOTE_THEME = 'bs3'
SUMMERNOTE_CONFIG = {
    # Using SummernoteWidget - iframe mode, default
    'iframe': True,

    # Or, you can set it as False to use SummernoteInplaceWidget by default - no iframe mode
    # In this case, you have to load Bootstrap/jQuery stuff by manually.
    # Use this when you're already using Bootstraip/jQuery based themes.
    # 'iframe': False,

    # You can put custom Summernote settings
    'summernote': {
        # As an example, using Summernote Air-mode
        'airMode': False,

        # Change editor size
        'width': '100%',
        'height': '480',

        'followingToolbar': False,

        # Customize toolbar buttons
        'toolbar': [
            ['style', ['style']],
            ['font', ['bold', 'italic', 'underline', 'superscript', 'subscript',
                      'strikethrough', 'add-text-tags', 'clear']],
            ['fontname', ['fontname']],
            ['fontsize', ['fontsize']],
            ['color', ['color']],
            ['para', ['ul', 'ol', 'listStyles', 'paragraph']],
            # ['height', ['height']],
            ['table', ['table']],
            ['insert', ['link', 'picture', 'videoAttributes', 'hr', 'faicon', 'math', ]],  # , 'nugget']],
            ['view', ['codeview']],
            ['help', ['help']],
        ],

        # You can also add custom settings for external plugins
        # 'print': {
        #     'stylesheetUrl': '/some_static_folder/printable.css',
        # },
        'codemirror': {
            'mode': 'htmlmixed',
            'lineNumbers': 'true',
            'lineWrapping': 'true',
            # You have to include theme file in 'css' or 'css_for_inplace' before using it.
            'theme': 'monokai',
        },
    },

    # Need authentication while uploading attachments.
    'attachment_require_authentication': True,
    'attachment_filesize_limit': 4096 * 4096,

    # Set `upload_to` function for attachments.
    # 'attachment_upload_to': my_custom_upload_to_func(),

    # Set custom storage class for attachments.
    # 'attachment_storage_class': 'my.custom.storage.class.name',

    # Set custom model for attachments (default: 'django_summernote.Attachment')
    # 'attachment_model': 'my.custom.attachment.model',  # must inherit 'django_summernote.AbstractAttachment'

    # You can disable attachment feature.
    # Currently only works for images anyway.  Turn on when it works with other files
    # Images can still be embedded with the image tool
    'disable_attachment': False,

    # Set `True` to return attachment paths in absolute URIs.
    'attachment_absolute_uri': False,

    # You can also add custom css/js for SummernoteInplaceWidget.
    # !!! Be sure to put {{ form.media }} in template before initiate summernote.
    'css_for_inplace': (
        '//cdnjs.cloudflare.com/ajax/libs/codemirror/5.29.0/theme/monokai.min.css',
        # os.path.join(STATIC_URL, 'css/custom_summernote_widget.css'),
        os.path.join(STATIC_URL, 'summernote-faicon/summernote-ext-faicon.css'),
        # os.path.join(STATIC_URL, 'summernote-ext-emoji-ajax/summernote-ext-emoji-ajax.css'),
        os.path.join(STATIC_URL, 'summernote-add-text-tags/summernote-add-text-tags.css'),
        os.path.join(STATIC_URL, 'summernote-list-styles/summernote-list-styles.css'),
        os.path.join(STATIC_URL, 'css/custom_summernote_widget.css'),
        '//cdnjs.cloudflare.com/ajax/libs/KaTeX/0.9.0/katex.min.css',
    ),
    'js_for_inplace': (
        os.path.join(STATIC_URL, 'summernote-faicon/summernote-ext-faicon.js'),
        # os.path.join(STATIC_URL, 'summernote-ext-emoji-ajax/summernote-ext-emoji-ajax.js'),
        os.path.join(STATIC_URL, 'js/summernote-video-attributes.js'),
        os.path.join(STATIC_URL, 'summernote-add-text-tags/summernote-add-text-tags.js'),
        os.path.join(STATIC_URL, 'js/summernote-image-shapes.js'),
        os.path.join(STATIC_URL, 'summernote-list-styles/summernote-list-styles.js'),
        os.path.join(STATIC_URL, 'js/summernote-table-styles.js'),
        os.path.join(STATIC_URL, 'js/summernote-table-headers.js'),
        # '//cdnjs.cloudflare.com/ajax/libs/KaTeX/0.9.0/katex.min.js', # included in base template
        os.path.join(STATIC_URL, 'js/summernote-math.js'),
        os.path.join(STATIC_URL, 'js/summernote-classes.js'),
    ),

    # Codemirror as codeview
    # If any codemirror settings are defined, it will include codemirror files automatically.
    'css': (
        '//cdnjs.cloudflare.com/ajax/libs/codemirror/5.29.0/theme/monokai.min.css',
        '//cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css',
        # os.path.join(STATIC_URL, 'css/font-awesome.min.css'),
        os.path.join(STATIC_URL, 'css/custom_common.css'),
        os.path.join(STATIC_URL, 'css/custom.css'),
        os.path.join(STATIC_URL, 'css/custom_summernote_iframe.css'),
        os.path.join(STATIC_URL, 'summernote-faicon/summernote-ext-faicon.css'),
        # os.path.join(STATIC_URL, 'summernote-ext-emoji-ajax/summernote-ext-emoji-ajax.css'),
        os.path.join(STATIC_URL, 'summernote-add-text-tags/summernote-add-text-tags.css'),
        os.path.join(STATIC_URL, 'summernote-list-styles/summernote-list-styles.css'),
        '//cdnjs.cloudflare.com/ajax/libs/KaTeX/0.9.0/katex.min.css',
    ),

    # To use external plugins,
    # Include them within `css` and `js`.
    'js': (
        os.path.join(STATIC_URL, 'summernote-faicon/summernote-ext-faicon.js'),
        # os.path.join(STATIC_URL, 'summernote-ext-emoji-ajax/summernote-ext-emoji-ajax.js'),
        os.path.join(STATIC_URL, 'js/summernote-video-attributes.js'),
        os.path.join(STATIC_URL, 'summernote-add-text-tags/summernote-add-text-tags.js'),
        os.path.join(STATIC_URL, 'js/summernote-image-shapes.js'),
        os.path.join(STATIC_URL, 'summernote-list-styles/summernote-list-styles.js'),
        os.path.join(STATIC_URL, 'js/summernote-table-styles.js'),
        os.path.join(STATIC_URL, 'js/summernote-table-headers.js'),
        '//cdnjs.cloudflare.com/ajax/libs/KaTeX/0.9.0/katex.min.js',
        os.path.join(STATIC_URL, 'js/summernote-math.js'),
    ),

    'popover': {
        'image': [
            ['custom', ['imageShapes']],
            ['imagesize', ['imageSize100', 'imageSize50', 'imageSize25']],
            ['float', ['floatLeft', 'floatRight', 'floatNone']],
            ['remove', ['removeMedia']]
        ],
        'link': [
            ['link', ['linkDialogShow', 'unlink']]
        ],
        'table': [
            ['add', ['addRowDown', 'addRowUp', 'addColLeft', 'addColRight']],
            ['delete', ['deleteRow', 'deleteCol', 'deleteTable']],
            ['custom', ['tableHeaders', 'tableStyles']]
        ],
    },

    # Lazy initialize
    # If you want to initialize summernote at the bottom of page, set this as True
    # and call `initSummernote()` on your page.
    # 'lazy': True,

}

# django-rseized
DJANGORESIZED_DEFAULT_QUALITY = 90
DJANGORESIZED_DEFAULT_SIZE = [256, 256]
DJANGORESIZED_DEFAULT_FORCE_FORMAT = None

# django-taggit
TAGGIT_CASE_INSENSITIVE = True


# DEBUG / DEVELOPMENT SPECIFIC SETTINGS #################################

if DEBUG:

    import socket
    INTERNAL_IPS = ['127.0.0.1', '0.0.0.0']

    # Solves an issue where django-debug-toolbar is not showing when running inside a docker container
    # See: https://gist.github.com/douglasmiranda/9de51aaba14543851ca3#gistcomment-2916867
    # get ip address for docker host
    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    for ip in ips:
        # replace last octet in IP with .1
        ip = '{}.1'.format(ip.rsplit('.', 1)[0])
        INTERNAL_IPS.append(ip)

    # DEBUG TOOLBAR
    MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware', ]
    INSTALLED_APPS += (
        'debug_toolbar',
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

    # DEBUG_TOOLBAR_CONFIG = {
    #     'SHOW_TOOLBAR_CALLBACK': lambda request: not request.is_ajax()
    # }


# TESTING ##################################################

TESTING = 'test' in sys.argv
if TESTING:
    # Use weaker password hasher for speeding up tests
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ]

    # django.test.override_settings does not simply work as expected.
    # overriding settings here instead
    CACHES['default'] = {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'test-loc'
    }
