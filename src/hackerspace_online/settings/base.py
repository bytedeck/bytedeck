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

INSTALLED_APPS = (

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

    # https://github.com/asaglimbeni/django-datetime-widget
    'datetimewidget',

    # django-djconfig.readthedocs.org/en/
    'djconfig',

    # https://github.com/yetty/django-embed-video
    # used for the EmbedVideoField that validates YouTube and Vimeo urls
    'embed_video',

    # https://github.com/applegrew/django-select2
    'django_select2',

    # https://github.com/matthisk/django-jchart
    'jchart',

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
    'suggestions',
    'djcytoscape',
    'portfolios',
    # 'tours',
)

# http://django-allauth.readthedocs.io/en/latest/installation.html#post-installation
#SITE_ID = 1
MIDDLEWARE_CLASSES = []

MIDDLEWARE_CLASSES += [
    # caching: https://docs.djangoproject.com/en/1.10/topics/cache/
    # 'django.middleware.cache.UpdateCacheMiddleware',
    # 'django.middleware.cache.FetchFromCacheMiddleware',

    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.auth.middleware.SessionAuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # used by django-date-time-widget
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'djconfig.middleware.DjConfigMiddleware',
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

                # "allauth" specific context processors
                # 0.22.0 http://django-allauth.readthedocs.io/en/latest/release-notes.html#id17
                # 'allauth.account.context_processors.account',
                # 'allauth.socialaccount.context_processors.socialaccount',

                'djconfig.context_processors.config',
            ],
            # 'string_if_invalid': 'DEBUG WARNING: undefined template variable [%s] not found',
        },
    },
]

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.memcached.MemcachedCache',
        'LOCATION': 'unix:/tmp/memcached.sock',
    },
    'select2': {
        'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
        'LOCATION': 'cache_table',
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

SITE_ID = 3

# AllAuth Configuration
SOCIALACCOUNT_PROVIDERS = \
    {'facebook':
         {'SCOPE': ['email', 'public_profile'],
          'AUTH_PARAMS': {'auth_type': 'reauthenticate'},
          'METHOD': 'oauth2',
          # 'LOCALE_FUNC': 'path.to.callable',
          'VERIFIED_EMAIL': False,
          'VERSION': 'v2.3'}}

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
# ACCOUNT_LOGOUT_ON_GET #(=False)
# Determines whether or not the user is automatically logged out by a mere GET request. See documentation for the LogoutView for details.
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True  # (=False)
# Determines whether or not the user is automatically logged out after changing the password. See documentation for Django’s session invalidation on password change. (Django 1.7+)
ACCOUNT_LOGOUT_REDIRECT_URL = LOGIN_URL  # (=”/”)
# The URL (or URL name) to return to after the user logs out. This is the counterpart to Django’s LOGIN_REDIRECT_URL.
# ACCOUNT_SIGNUP_FORM_CLASS #(=None)
# A string pointing to a custom form class (e.g. ‘myapp.forms.SignupForm’) that is used during signup to ask the user for additional input (e.g. newsletter signup, birth date). This class should implement a def signup(self, request, user) method, where user represents the newly signed up user.
# ACCOUNT_SIGNUP_PASSWORD_VERIFICATION #(=True)
# When signing up, let the user type in their password twice to avoid typo’s.
# ACCOUNT_UNIQUE_EMAIL #(=True)
# Enforce uniqueness of e-mail addresses.
# ACCOUNT_USER_MODEL_USERNAME_FIELD #(=”username”)
# The name of the field containing the username, if any. See custom user models.
# ACCOUNT_USER_MODEL_EMAIL_FIELD #(=”email”)
# The name of the field containing the email, if any. See custom user models.
# ACCOUNT_USER_DISPLAY #(=a callable returning user.get_username())
# A callable (or string of the form ‘some.module.callable_name’) that takes a user as its only argument and returns the display name of the user. The default implementation returns user.get_username().
# ACCOUNT_USERNAME_MIN_LENGTH #(=4)
# An integer specifying the minimum allowed length of a username.
# ACCOUNT_USERNAME_BLACKLIST #(=[])
# A list of usernames that can’t be used by user.
# ACCOUNT_USERNAME_REQUIRED #(=True)
# The user is required to enter a username when signing up. Note that the user will be asked to do so even if ACCOUNT_AUTHENTICATION_METHOD is set to email. Set to False when you do not wish to prompt the user to enter a username.
# ACCOUNT_PASSWORD_INPUT_RENDER_VALUE #(=False)
# render_value parameter as passed to PasswordInput fields.
# ACCOUNT_PASSWORD_MIN_LENGTH = 6 #(=1)
# An integer specifying the minimum password length.
# ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION #(=True)
# The default behaviour is to automatically log users in once they confirm their email address. Note however that this only works when confirming the email address immediately after signing up, assuming users didn’t close their browser or used some sort of private browsing mode.
# By changing this setting to False they will not be logged in, but redirected to the ACCOUNT_EMAIL_CONFIRMATION_ANONYMOUS_REDIRECT_URL
# ACCOUNT_SESSION_REMEMBER #(=None)
# Controls the life time of the session. Set to None to ask the user (“Remember me?”), False to not remember, and True to always remember.
# ACCOUNT_SESSION_COOKIE_AGE #(=1814400)
# How long before the session cookie expires in seconds. Defaults to 1814400 seconds, or 3 weeks.
# SOCIALACCOUNT_ADAPTER #(=”allauth.socialaccount.adapter.DefaultSocialAccountAdapter”)
# Specifies the adapter class to use, allowing you to alter certain default behaviour.
# SOCIALACCOUNT_QUERY_EMAIL #(=ACCOUNT_EMAIL_REQUIRED)
# Request e-mail address from 3rd party account provider? E.g. using OpenID AX, or the Facebook “email” permission.
# SOCIALACCOUNT_AUTO_SIGNUP #(=True)
# Attempt to bypass the signup form by using fields (e.g. username, email) retrieved from the social account provider. If a conflict arises due to a duplicate e-mail address the signup form will still kick in.
# SOCIALACCOUNT_EMAIL_REQUIRED #(=ACCOUNT_EMAIL_REQUIRED)
# The user is required to hand over an e-mail address when signing up using a social account.
# SOCIALACCOUNT_EMAIL_VERIFICATION #(=ACCOUNT_EMAIL_VERIFICATION)
# As ACCOUNT_EMAIL_VERIFICATION, but for social accounts.
# SOCIALACCOUNT_FORMS #(={})
# Used to override forms, for example: {‘signup’: ‘myapp.forms.SignupForm’}
# SOCIALACCOUNT_PROVIDERS #(= dict)
# Dictionary containing provider specific settings.
# SOCIALACCOUNT_STORE_TOKENS #(=True)
# Indicates whether or not the access tokens are stored in the database.

#################################
#
# SUMMERNOTE WYSIWYG EDITOR
# https://github.com/summernote/django-summernote
#
#################################

SUMMERNOTE_CONFIG = {
    # Using SummernoteWidget - iframe mode
    'iframe': True,  # or set False to use SummernoteInplaceWidget - no iframe mode
    # need iframe for embedding youtube

    # Using Summernote Air-mode
    'airMode': False,

    # Use native HTML tags (`<b>`, `<i>`, ...) instead of style attributes
    # (Firefox, Chrome only)
    # 'styleWithTags': True,

    # Set text direction : 'left to right' is default.
    'direction': 'ltr',

    # Change editor size
    'width': '100%',
    'height': '460',

    # Use proper language setting automatically (default)
    'lang': None,

    # Or, set editor language/locale forcely
    # 'lang': 'ko-KR',

    # Customize toolbar buttons
    'toolbar': [
        ['style', ['style']],
        ['font', ['bold', 'italic', 'underline', 'superscript', 'subscript',
                  'strikethrough', 'clear']],
        ['fontname', ['fontname']],
        ['fontsize', ['fontsize']],
        ['color', ['color']],
        ['para', ['ul', 'ol', 'paragraph']],
        ['height', ['height']],
        ['table', ['table']],
        ['insert', ['link', 'picture', 'videoAttributes', 'hr', 'faicon', 'emoji']], #, 'nugget']],
        ['view', ['codeview']],
        ['help', ['help']],
    ],

    # customize popover options:
    # http://summernote.org/deep-dive/#custom-toolbar-popover
    # 'popover': {
    #     'image': [
    #         ['imagesize', ['imageSize100', 'imageSize50', 'imageSize25', 'imageSize15']],
    #         ['float', ['floatLeft', 'floatRight', 'floatNone']],
    #         ['remove', ['removeMedia']]
    #     ],
    # },

    # # https://github.com/pHAlkaline/summernote-plugins/tree/master/plugins/nugget
    # 'nugget': {
    #     'list': [  # list of your nuggets
    #         '[[Test Code]]',
    #         '[[code nugget 2]]',
    #         '[[code nugget 3]]'
    #     ]
    # },

    # Need authentication while uploading attachments.
    'attachment_require_authentication': True,

    'attachment_filesize_limit': 4096 * 4096,

    # Set `upload_to` function for attachments.
    # 'attachment_upload_to': my_custom_upload_to_func(),

    # Set custom storage class for attachments.
    # 'attachment_storage_class': 'my.custom.storage.class.name',

    # Set custom model for attachments (default: 'django_summernote.Attachment')
    # 'attachment_model': 'my.custom.attachment.model',
    # must inherit 'django_summernote.AbstractAttachment'

    # Set common css/js media files
    # 'external_css': (
    #     '//cdnjs.cloudflare.com/ajax/libs/codemirror/3.20.0/codemirror.css',
    #     '//cdnjs.cloudflare.com/ajax/libs/codemirror/3.20.0/theme/monokai.css',
    # ),
    # 'external_js': (
    #     '//cdnjs.cloudflare.com/ajax/libs/codemirror/3.20.0/codemirror.js',
    #     '//cdnjs.cloudflare.com/ajax/libs/codemirror/3.20.0/mode/xml/xml.js',
    #     '//cdnjs.cloudflare.com/ajax/libs/codemirror/2.36.0/formatting.js',
    # ),
    # 'internal_css': (
    #     # os.path.join(STATIC_URL, 'django_summernote/summernote.css'),
    #     # os.path.join(STATIC_URL, 'css/font-awesome.min.css'),
    # ),
    # 'internal_js': (
    #     os.path.join(STATIC_URL, 'django_summernote/jquery.ui.widget.js'),
    #     os.path.join(STATIC_URL, 'django_summernote/jquery.iframe-transport.js'),
    #     os.path.join(STATIC_URL, 'django_summernote/jquery.fileupload.js'),
    #     os.path.join(STATIC_URL, 'django_summernote/summernote.min.js'),
    # ),
    #
    # You can add custom css/js for SummernoteWidget.
    'css': (
        # '//cdnjs.cloudflare.com/ajax/libs/codemirror/3.20.0/codemirror.css',
        # '//cdnjs.cloudflare.com/ajax/libs/codemirror/3.20.0/theme/monokai.css',
        os.path.join(STATIC_URL, 'css/font-awesome.min.css'),
        os.path.join(STATIC_URL, 'css/custom_common.css'),
        os.path.join(STATIC_URL, 'css/custom.css'),
        os.path.join(STATIC_URL, 'css/custom_summernote_widget.css'),
        os.path.join(STATIC_URL, 'summernote-faicon/summernote-ext-faicon.css'),
        os.path.join(STATIC_URL, 'summernote-ext-emoji-ajax/summernote-ext-emoji-ajax.css'),
    ),
    'js': (
        # os.path.join(STATIC_URL, 'codemirror/lib/codemirror.js'),
        # os.path.join(STATIC_URL, 'codemirror/mode/javascript/javascript.js'),
        # '//cdnjs.cloudflare.com/ajax/libs/codemirror/3.20.0/codemirror.js',
        # '//cdnjs.cloudflare.com/ajax/libs/codemirror/3.20.0/mode/xml/xml.js',
        # '//cdnjs.cloudflare.com/ajax/libs/codemirror/2.36.0/formatting.js',
        os.path.join(STATIC_URL, 'summernote-faicon/summernote-ext-faicon.js'),
        os.path.join(STATIC_URL, 'js/summernote-ext-nugget.js'),
        os.path.join(STATIC_URL, 'summernote-ext-emoji-ajax/summernote-ext-emoji-ajax.js'),
        os.path.join(STATIC_URL, 'js/summernote-video-attributes.js'),
    ),

    # And also for SummernoteInplaceWidget.
    # !!! Be sure to put {{ form.media }} in template before initiate summernote.
    # 'css_for_inplace': (
    # ),
    # 'js_for_inplace': (
    # ),

    # You can disable file upload feature.
    # 'disable_upload': False,

    # Codemirror as codeview
    'codemirror': {
        # Please visit http://summernote.org/examples/#codemirror-as-codeview
        'theme': 'monokai',
    },
}


