from django.utils.six import text_type

from tags.widgets import TaggitSelect2Widget

from django_tenants.test.cases import TenantTestCase


class TestTaggitSelect2Widget(TenantTestCase):

    def test_get_url(self):
        widget = TaggitSelect2Widget()
        assert isinstance(widget.get_url(), text_type)

    def test_tag_attrs(self):
        widget = TaggitSelect2Widget()
        output = widget.render('name', 'value')
        assert 'data-minimum-input-length="1"' in output
        assert 'data-tags=","' in output

    def test_custom_tag_attrs(self):
        widget = TaggitSelect2Widget(attrs={'data-minimum-input-length': '3'})
        output = widget.render('name', 'value')
        assert 'data-minimum-input-length="3"' in output
