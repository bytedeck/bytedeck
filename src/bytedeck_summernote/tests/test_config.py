"""Tests for the editor's Summernote setup in bytedeck_summernote/config.py (#2913).

The plugins live in static/bytedeck_summernote/plugins/, one folder each, and config.py lists them
once for both kinds of editor. These tests check that list against the folders and the README, and
that the site's SUMMERNOTE_CONFIG is the one config.py builds.
"""

import os

from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase

import bytedeck_summernote
from bytedeck_summernote.config import PLUGINS, PLUGINS_STATIC, plugin_files, summernote_config

#: The plugins' folder on disk.
PLUGINS_DIR = os.path.join(os.path.dirname(bytedeck_summernote.__file__), 'static', PLUGINS_STATIC)


class SummernoteConfigTest(SimpleTestCase):
    """The plugins config.py lists are the ones in the plugins' folder, loaded by both editors."""

    def test_summernote_config__is_the_sites(self):
        """The site's SUMMERNOTE_CONFIG is the one config.py builds. django-summernote adds its own
        defaults to it as it loads (the editor's language, for one), so what config.py sets is
        compared, down into the settings handed to the editor itself."""
        site = settings.SUMMERNOTE_CONFIG
        for key, value in summernote_config(settings.STATIC_URL).items():
            with self.subTest(key=key):
                if key == 'summernote':
                    for option, setting in value.items():
                        self.assertEqual(site['summernote'][option], setting)
                else:
                    self.assertEqual(site[key], value)

    def test_plugin_files__every_file_is_served(self):
        """Every script and stylesheet the plugins list is a static file the site serves."""
        for path in plugin_files(settings.STATIC_URL, 'js') + plugin_files(settings.STATIC_URL, 'css'):
            with self.subTest(path=path):
                self.assertIsNotNone(finders.find(path[len(settings.STATIC_URL):]))

    def test_plugins__every_folder_is_loaded(self):
        """Every plugin folder is in the list, so none sits there unused, and each listed folder
        holds exactly the files listed for it."""
        folders = sorted(name for name in os.listdir(PLUGINS_DIR) if os.path.isdir(os.path.join(PLUGINS_DIR, name)))
        self.assertEqual(folders, sorted(plugin[0] for plugin in PLUGINS))
        for name, scripts, stylesheets in PLUGINS:
            with self.subTest(plugin=name):
                self.assertEqual(sorted(os.listdir(os.path.join(PLUGINS_DIR, name))), sorted(scripts + stylesheets))

    def test_plugins__every_plugin_is_described(self):
        """The plugins' README has a section for each one."""
        with open(os.path.join(PLUGINS_DIR, 'README.md')) as readme:
            headings = [line[len('### '):].strip() for line in readme if line.startswith('### ')]
        self.assertEqual(headings, sorted(plugin[0] for plugin in PLUGINS))

    def test_summernote_config__both_editors_load_the_same_plugins(self):
        """The iframe editor and the inplace editor load the same plugins, in the same order."""
        config = summernote_config('/static/')
        for kind, iframe, inplace in (('js', 'js', 'js_for_inplace'), ('css', 'css', 'css_for_inplace')):
            plugins = plugin_files('/static/', kind)
            with self.subTest(kind=kind):
                self.assertEqual([path for path in config[iframe] if path in plugins], list(plugins))
                self.assertEqual([path for path in config[inplace] if path in plugins], list(plugins))

    def test_summernote_config__iframe_loads_katex_before_the_math_plugin(self):
        """The iframe is a page of its own, so it loads KaTeX and js/note-math.js itself, before the
        math plugin that uses them. The inplace editor's page loads both already."""
        js = summernote_config('/static/')['js']
        math = js.index('/static/bytedeck_summernote/plugins/math/summernote-math.js')
        self.assertLess(js.index('/static/katex/katex-0.18.1.min.js'), math)
        self.assertLess(js.index('/static/js/note-math.js'), math)
