
from tags.widgets import TaggitSelect2Widget

from hackerspace_online.tests.utils import ByteDeckTenantTestCase


class TestTaggitSelect2Widget(ByteDeckTenantTestCase):

    def test_get_url(self):
        widget = TaggitSelect2Widget()
        assert isinstance(widget.get_url(), str)

    def test_tag_attrs(self):
        widget = TaggitSelect2Widget()
        output = widget.render('name', 'value')
        assert 'data-minimum-input-length="1"' in output
        assert 'data-tags=","' in output

    def test_custom_tag_attrs(self):
        widget = TaggitSelect2Widget(attrs={'data-minimum-input-length': '3'})
        output = widget.render('name', 'value')
        assert 'data-minimum-input-length="3"' in output
