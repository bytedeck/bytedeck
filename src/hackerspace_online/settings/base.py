"""
Django settings for hackerspace_online project.

For more information on this file, see
https://docs.djangoproject.com/en/1.8/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/1.8/ref/settings/
"""

# Build paths inside the project like this: os.path.join(BASE_DIR, ...)
import os

# root of project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/1.8/howto/deployment/checklist/

# Define secret key in local and production files
# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY = ''


# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG set in local or production file
# DEBUG = True


# ALLOWED_HOSTS = []

# EMAIL_HOST = 'smtp.gmail.com'
# EMAIL_HOST_USER = 'timberline.hackerspace@gmail.com'
# EMAIL_HOST_PASSWORD =""
# EMAIL_PORT = 587
# EMAIL_USE_TLS = True

# Application definition
SHARED_APPS = (
    'django_tenants',
    'tenant',
    'django.contrib.contenttypes',

    'django.contrib.sites',

    'grappelli',
    'crispy_forms',
    'bootstrap_datepicker_plus',
    'embed_video',
    'django_select2',
    'jchart',
    'url_or_relative_url_field',
    'import_export',
    'colorful',

)

TENANT_APPS = (
    'django.contrib.contenttypes',

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
    # placing here instead of shared means...?
    'django_celery_beat',

    'attachments',
    'hackerspace_online',
    'django_summernote',

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
)


INSTALLED_APPS = (
    'django_tenants',
    'tenant.apps.TenantConfig',

    # http://django-grappelli.readthedocs.org/en/latest/quickstart.html
    'grappelli',

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
    # 'allauth.socialaccount.providers.google',
    # 'allauth.socialaccount.providers.facebook',

    # http://django-crispy-forms.readthedocs.org/en/latest/install.html
    'crispy_forms',

    # https://github.com/summernote/django-summernote
    'django_summernote',

    # https://github.com/monim67/django-bootstrap-datepicker-plus
    'bootstrap_datepicker_plus',

    # https://github.com/yetty/django-embed-video
    # used for the EmbedVideoField that validates YouTube and Vimeo urls
    'embed_video',

    # https://github.com/applegrew/django-select2
    'django_select2',

    # https://github.com/matthisk/django-jchart
    'jchart',

    # https://github.com/timonweb/django-url-or-relative-url-field
    'url_or_relative_url_field',

    # https://django-import-export.readthedocs.io
    'import_export',

    'django_celery_beat',

    # https://github.com/charettes/django-colorful
    'colorful',

    # django-attachments
    'attachments',

    # hackerspace_online.apps.HackerspaceConfig
    'hackerspace_online',

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
)

MIDDLEWARE = [
    'django_tenants.middleware.main.TenantMainMiddleware',
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

                'siteconfig.context_processors.config',
            ],
            # 'string_if_invalid': 'DEBUG WARNING: undefined template variable [%s] not found',
        },
    },
]

# Redis:
REDIS_HOST = os.environ.get('REDIS_HOST', '127.0.0.1')
REDIS_PORT = os.environ.get('REDIS_PORT', '6379')

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://{}:{}/1".format(REDIS_HOST, REDIS_PORT),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        'KEY_FUNCTION': 'django_tenants.cache.make_key',
        'REVERSE_KEY_FUNCTION': 'django_tenants.cache.reverse_key'
    },
    'select2': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': "redis://{}:{}/1".format(REDIS_HOST, REDIS_PORT),
        'TIMEOUT': None,
        'KEY_FUNCTION': 'django_tenants.cache.make_key',
        'REVERSE_KEY_FUNCTION': 'django_tenants.cache.reverse_key'
    }
}
SELECT2_CACHE_BACKEND = 'select2'

AUTHENTICATION_BACKENDS = (

    # Needed to login by username in Django admin, regardless of `allauth`
    'django.contrib.auth.backends.ModelBackend',

    # `allauth` specific authentication methods, such as login by e-mail
    'allauth.account.auth_backends.AuthenticationBackend',

)

WSGI_APPLICATION = 'hackerspace_online.wsgi.application'

# Database
# https://docs.djangoproject.com/en/1.8/ref/settings/#databases
# define in local or production


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
STATIC_URL = '/static/'

CRISPY_TEMPLATE_PACK = 'bootstrap3'

SITE_ID = 1

# AllAuth Configuration
# SOCIALACCOUNT_PROVIDERS = \
#     {'facebook':
#          {'SCOPE': ['email', 'public_profile'],
#           'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
#           'METHOD': 'oauth2',
#           # 'LOCALE_FUNC': 'path.to.callable',
#           'VERIFIED_EMAIL': False,
#           'VERSION': 'v2.3'}
#      }

# https://django-allauth.readthedocs.org/en/latest/configuration.html
LOGIN_REDIRECT_URL = '/'
LOGIN_URL = '/'
# ACCOUNT_ADAPTER #(=”allauth.account.adapter.DefaultAccountAdapter”)
# Specifies the adapter class to use, allowing you to alter certain default behaviour.
ACCOUNT_AUTHENTICATION_METHOD = "username"  # (=”username” | “email” | “username_email”)
# Specifies the login method to use – whether the user logs in by entering their username, e-mail address, or either one of both. Setting this to “email” requires ACCOUNT_EMAIL_REQUIRED=True
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
ACCOUNT_EMAIL_VERIFICATION = None  # (=”optional”)
# Determines the e-mail verification method during signup – choose one of “mandatory”, “optional”, or “none”. When set to “mandatory” the user is blocked from logging in until the email address is verified. Choose “optional” or “none” to allow logins with an unverified e-mail address. In case of “optional”, the e-mail verification mail is still sent, whereas in case of “none” no e-mail verification mails are sent.
# ACCOUNT_EMAIL_SUBJECT_PREFIX #(=”[Site] ”)
# Subject-line prefix to use for email messages sent. By default, the name of the current Site (django.contrib.sites) is used.
# ACCOUNT_DEFAULT_HTTP_PROTOCOL  #(=”http”)
# The default protocol used for when generating URLs, e.g. for the password forgotten procedure. Note that this is a default only – see the section on HTTPS for more information.
# ACCOUNT_FORMS #(={})
# Used to override forms, for example: {‘login’: ‘myapp.forms.LoginForm’}
ACCOUNT_FORMS = {'signup': 'hackerspace_online.forms.CustomSignupForm'}
# ACCOUNT_LOGOUT_ON_GET #(=False)
# Determines whether or not the user is automatically logged out by a mere GET request. See documentation for the LogoutView for details.
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True  # (=False)
# Determines whether or not the user is automatically logged out after changing the password. See documentation for Django’s session invalidation on password change. (Django 1.7+)
ACCOUNT_LOGOUT_REDIRECT_URL = LOGIN_URL  # (=”/”)

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
    ),

    # Codemirror as codeview
    # If any codemirror settings are defined, it will include codemirror files automatically.
    'css': (
        '//cdnjs.cloudflare.com/ajax/libs/codemirror/5.29.0/theme/monokai.min.css',
        os.path.join(STATIC_URL, 'css/font-awesome.min.css'),
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

# Celery:
CELERY_BROKER_URL = "redis://{}:{}/0".format(REDIS_HOST, REDIS_PORT)
CELERY_ACCEPT_CONTENT = ['application/json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'

CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_MAX_RETRIES = 10
CELERY_TASKS_BUNCH_SIZE = 10

# allowed delay between conditions met updates for all users:
CONDITIONS_UPDATE_COUNTDOWN = 60 * 1  # In sec., wait before start next 'big' update for all conditions, if it's going to start - all other updates could be skipped

# Django Postman
POSTMAN_DISALLOW_ANONYMOUS = True
# POSTMAN_NOTIFICATION_APPROVAL = 'path.to.function.accepts.user.action.site.returns.boolean'


def POSTMAN_NOTIFICATION_APPROVAL(u): return u.profile.get_messages_by_email


POSTMAN_AUTO_MODERATE_AS = True  # only student <> teacher interactions will be allowed, so no need to moderate student <> student
POSTMAN_NAME_USER_AS = 'id'  # need to use key/id for select2 widget
# POSTMAN_SHOW_USER_AS = lambda u: u.id

# https://github.com/charettes/django-colorful
GRAPPELLI_CLEAN_INPUT_TYPES = False


POSTGRES_HOST = os.environ.get('POSTGRES_HOST', '127.0.0.1')
POSTGRES_PORT = os.environ.get('POSTGRES_PORT', '5432')
POSTGRES_DB_NAME = os.environ.get('POSTGRES_DB_NAME', 'postgres')
POSTGRES_USER = os.environ.get('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.environ.get('POSTGRES_PASSWORD', 'hellonepal')

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

TENANT_MODEL = "tenant.Tenant"
TENANT_DOMAIN_MODEL = "tenant.TenantDomain"

# See this: https://github.com/timberline-secondary/hackerspace/issues/388
# The design choice for media files it serving all the media files from one directory instead of separate directory for each tenant. That's why getting rid of # the warning
SILENCED_SYSTEM_CHECKS = ['django_tenants.W003']
