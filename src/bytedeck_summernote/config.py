"""The editor's Summernote setup: its toolbar, menus, plugins and attachments (#2913).

hackerspace_online/settings.py sets SUMMERNOTE_CONFIG from summernote_config(), so what the editor
shows and can do is set up here, with the editor. The plugins' own files are in
static/bytedeck_summernote/plugins/, one folder each, described in that folder's README.md.

This module is read while Django's settings are being built, so it imports nothing from Django.
"""

import os

#: The folder of the plugins' files, under the app's static folder.
PLUGINS_STATIC = 'bytedeck_summernote/plugins'

#: The plugins, in the order both kinds of editor load them: each one's folder, then its scripts
#: and its stylesheets, by file name in that folder.
PLUGINS = (
    ('faicon', ('summernote-ext-faicon.js',), ('summernote-ext-faicon.css',)),
    ('video-attributes', ('summernote-video-attributes.js',), ()),
    ('add-text-tags', ('summernote-add-text-tags.js',), ('summernote-add-text-tags.css',)),
    ('image-shapes', ('summernote-image-shapes.js',), ()),
    ('image-source', ('summernote-image-source.js',), ()),
    ('image-link', ('summernote-image-link.js',), ()),
    ('image-align', ('summernote-image-align.js',), ()),
    ('list-styles', ('summernote-list-styles.js',), ('summernote-list-styles.css',)),
    ('table-styles', ('summernote-table-styles.js',), ()),
    ('table-headers', ('summernote-table-headers.js',), ()),
    ('math', ('summernote-math.js',), ()),
    ('keep-caret', ('summernote-keep-caret.js',), ()),
)


def plugin_files(static_url, kind):
    """Return the URLs of the plugins' scripts or stylesheets, in the order they load.

    Args:
        static_url (str): the site's STATIC_URL.
        kind (str): 'js' for the scripts, 'css' for the stylesheets.

    Returns:
        tuple: the files' URLs.
    """
    index = {'js': 1, 'css': 2}[kind]
    return tuple(
        os.path.join(static_url, PLUGINS_STATIC, plugin[0], name)
        for plugin in PLUGINS
        for name in plugin[index]
    )


def summernote_config(static_url):
    """Return django-summernote's SUMMERNOTE_CONFIG for the site.

    Args:
        static_url (str): the site's STATIC_URL, which the editor's own files are served under.

    Returns:
        dict: the editor's settings.
    """
    # The Font Awesome 4.7.0 icon list (window.faIcons) that the faicon plugin reads, shared with
    # the icon picker on other forms (utilities/fa_icon_widget.py).
    fa_icons = os.path.join(static_url, 'js/fa_icons_4.7.0.js')
    return {
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

            # The menus that pop up over a clicked image, link or table. They belong here with the toolbar:
            # django-summernote hands the editor only this 'summernote' dict (#268). The image menu's size
            # buttons carry Summernote 0.8.20's names, and "custom", "imagelink" and "imagealign" hold the
            # buttons our plugins add.
            'popover': {
                'image': [
                    ['custom', ['imageShapes', 'imageSource']],
                    ['imagelink', ['imageLink', 'imageUnlink']],
                    ['resize', ['resizeFull', 'resizeHalf', 'resizeQuarter', 'resizeNone']],
                    ['float', ['floatLeft', 'floatRight', 'floatNone']],
                    ['imagealign', ['imageAlignLeft', 'imageAlignCenter', 'imageAlignRight']],
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
            *plugin_files(static_url, 'css'),
            os.path.join(static_url, 'css/custom_summernote_widget.css'),
            # KaTeX's stylesheet comes from templates/head_css.html on every page
        ),
        'js_for_inplace': (
            fa_icons,
            # KaTeX itself, and js/note-math.js, come from templates/javascript.html on every page
            *plugin_files(static_url, 'js'),
        ),

        # Codemirror as codeview
        # If any codemirror settings are defined, it will include codemirror files automatically.
        # The iframe is a page of its own, so it loads the site's stylesheets and KaTeX itself.
        'css': (
            '//cdnjs.cloudflare.com/ajax/libs/codemirror/5.29.0/theme/monokai.min.css',
            '//cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css',
            os.path.join(static_url, 'css/custom_common.css'),
            os.path.join(static_url, 'css/custom.css'),
            os.path.join(static_url, 'css/custom_summernote_iframe.css'),
            *plugin_files(static_url, 'css'),
            os.path.join(static_url, 'katex/katex-0.18.1.min.css'),  # the KaTeX templates/head_css.html loads
        ),

        # To use external plugins,
        # Include them within `css` and `js`.
        'js': (
            fa_icons,
            os.path.join(static_url, 'katex/katex-0.18.1.min.js'),  # the KaTeX templates/javascript.html loads
            os.path.join(static_url, 'js/note-math.js'),
            *plugin_files(static_url, 'js'),
        ),

        # Lazy initialize
        # If you want to initialize summernote at the bottom of page, set this as True
        # and call `initSummernote()` on your page.
        # 'lazy': True,
    }
