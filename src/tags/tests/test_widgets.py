
from tags.widgets import TaggitSelect2Widget

from hackerspace_online.tests.utils import ByteDeckTenantTestCase


class TestTaggitSelect2Widget(ByteDeckTenantTestCase):

    def test_get_url__returns_string(self):
        """The widget's get_url returns a string URL."""
        widget = TaggitSelect2Widget()
        assert isinstance(widget.get_url(), str)

    def test_render__default_tag_attrs(self):
        """Rendered widget includes the default select2 tag data attributes."""
        widget = TaggitSelect2Widget()
        output = widget.render('name', 'value')
        assert 'data-minimum-input-length="1"' in output
        assert 'data-tags=","' in output

    def test_render__custom_tag_attrs(self):
        """Custom attrs passed to the widget override the rendered defaults."""
        widget = TaggitSelect2Widget(attrs={'data-minimum-input-length': '3'})
        output = widget.render('name', 'value')
        assert 'data-minimum-input-length="3"' in output

    def test_options__splits_raw_comma_separated_string(self):
        """A raw (unvalidated) comma-separated string is split into individual tag option values."""
        widget = TaggitSelect2Widget()
        self.assertEqual(list(widget.options('tags', 'alpha,beta')), ['alpha', 'beta'])

    def test_options__skips_empty_values(self):
        """Empty entries in the value list are skipped, yielding only the non-empty tag option values."""
        widget = TaggitSelect2Widget()
        self.assertEqual(list(widget.options('tags', ['', 'gamma'])), ['gamma'])
