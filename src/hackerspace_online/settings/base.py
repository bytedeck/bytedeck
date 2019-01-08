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

    # https://github.com/timonweb/django-url-or-relative-url-field
    'url_or_relative_url_field',

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
    'utilities',
    # 'tours',
)

# http://django-allauth.readthedocs.io/en/latest/installation.html#post-installation
#SITE_ID = 1
MIDDLEWARE = []

MIDDLEWARE += [
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


#################################
#
# SUMMERNOTE WYSIWYG EDITOR
# https://github.com/summernote/django-summernote
#
#################################

SUMMERNOTE_CONFIG = {
    # Using SummernoteWidget - iframe mode, default
    # 'iframe': True,

    # Or, you can set it as False to use SummernoteInplaceWidget by default - no iframe mode
    # In this case, you have to load Bootstrap/jQuery stuff by manually.
    # Use this when you're already using Bootstraip/jQuery based themes.
    'iframe': False,

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
                      'strikethrough', 'clear']],
            ['fontname', ['fontname']],
            ['fontsize', ['fontsize']],
            ['color', ['color']],
            ['para', ['ul', 'ol', 'paragraph']],
            ['height', ['height']],
            ['table', ['table']],
            ['insert', ['link', 'picture', 'hr']],  # , 'nugget']],
            ['view', ['codeview']],
            ['help', ['help']],
        ],

        # You can also add custom settings for external plugins
        # 'print': {
        #     'stylesheetUrl': '/some_static_folder/printable.css',
        # },

    },

    # Need authentication while uploading attachments.
    # 'attachment_require_authentication': True,

    # Set `upload_to` function for attachments.
    # 'attachment_upload_to': my_custom_upload_to_func(),

    # Set custom storage class for attachments.
    # 'attachment_storage_class': 'my.custom.storage.class.name',

    # Set custom model for attachments (default: 'django_summernote.Attachment')
    # 'attachment_model': 'my.custom.attachment.model',  # must inherit 'django_summernote.AbstractAttachment'

    # You can disable attachment feature.
    # 'disable_attachment': False,

    # You can add custom css/js for SummernoteWidget.
    # 'css': (
    # ),
    # 'js': (
    # ),

    # You can also add custom css/js for SummernoteInplaceWidget.
    # !!! Be sure to put {{ form.media }} in template before initiate summernote.
    # 'css_for_inplace': (
    # ),
    # 'js_for_inplace': (
    # ),

    # Codemirror as codeview
    # If any codemirror settings are defined, it will include codemirror files automatically.
    'css': {
        '//cdnjs.cloudflare.com/ajax/libs/codemirror/5.29.0/theme/monokai.min.css',
        # os.path.join(STATIC_URL, 'summernote-list-styles/summernote-list-styles.css'),
    },

    # To use external plugins,
    # Include them within `css` and `js`.
    'js': {
        # os.path.join(STATIC_URL, 'js/summernote-video-attributes.js'),
        # os.path.join(STATIC_URL, 'js/summernote-table-styles.js'),
        # os.path.join(STATIC_URL, 'summernote-list-styles/summernote-list-styles.js'),
    },


    'codemirror': {
        'mode': 'htmlmixed',
        'lineNumbers': 'true',

        # You have to include theme file in 'css' or 'css_for_inplace' before using it.
        'theme': 'monokai',
    },

    # Lazy initialize
    # If you want to initialize summernote at the bottom of page, set this as True
    # and call `initSummernote()` on your page.
    # 'lazy': True,

}


SUMMERNOTE_CONFIG_OLD = {
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
                  'strikethrough', 'add-text-tags', 'clear']],
        ['fontname', ['fontname']],
        ['fontsize', ['fontsize']],
        ['color', ['color']],
        ['para', ['ul', 'ol', 'listStyles', 'paragraph']],
        ['height', ['height']],
        ['table', ['table']],
        ['insert', ['link', 'picture', 'videoAttributes', 'hr', 'faicon', 'emoji', 'math']], #, 'nugget']],
        ['view', ['codeview']],
        ['help', ['help']],
    ],

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
        os.path.join(STATIC_URL, 'summernote-add-text-tags/summernote-add-text-tags.css'),
        os.path.join(STATIC_URL, 'summernote-list-styles/summernote-list-styles.css'),
        '//cdnjs.cloudflare.com/ajax/libs/codemirror/5.29.0/theme/monokai.min.css',
        '//cdnjs.cloudflare.com/ajax/libs/KaTeX/0.9.0/katex.min.css',
    ),
    'js': (
        # os.path.join(STATIC_URL, 'codemirror/lib/codemirror.js'),
        # os.path.join(STATIC_URL, 'codemirror/mode/javascript/javascript.js'),
        # '//cdnjs.cloudflare.com/ajax/libs/codemirror/3.20.0/codemirror.js',
        # '//cdnjs.cloudflare.com/ajax/libs/codemirror/3.20.0/mode/xml/xml.js',
        # '//cdnjs.cloudflare.com/ajax/libs/codemirror/2.36.0/formatting.js',
        os.path.join(STATIC_URL, 'summernote-faicon/summernote-ext-faicon.js'),
        # os.path.join(STATIC_URL, 'js/summernote-ext-nugget.js'),
        os.path.join(STATIC_URL, 'summernote-ext-emoji-ajax/summernote-ext-emoji-ajax.js'),
        os.path.join(STATIC_URL, 'js/summernote-video-attributes.js'),
        os.path.join(STATIC_URL, 'summernote-add-text-tags/summernote-add-text-tags.js'),
        os.path.join(STATIC_URL, 'js/summernote-image-shapes.js'),
        os.path.join(STATIC_URL, 'summernote-list-styles/summernote-list-styles.js'),
        os.path.join(STATIC_URL, 'js/summernote-table-styles.js'),
        os.path.join(STATIC_URL, 'js/summernote-table-headers.js'),
        '//cdnjs.cloudflare.com/ajax/libs/KaTeX/0.9.0/katex.min.js',
        os.path.join(STATIC_URL, 'js/summernote-math.js'),
    ),

    # And also for SummernoteInplaceWidget.
    # !!! Be sure to put {{ form.media }} in template before initiate summernote.
    # 'css_for_inplace': (
    # ),
    # 'js_for_inplace': (
    # ),

    # You can disable file upload feature.
    # 'disable_upload': False,

    # # Codemirror as codeview
    # # http://summernote.org/examples/#codemirror-as-codeview
    # 'codemirror': {
    #     'mode': 'htmlmixed',
    #     'lineNumbers': 'true',
    #     'theme': 'monokai',
    #     'lineWrapping': 'true'
    # },
}


