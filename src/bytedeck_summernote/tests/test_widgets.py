from django.urls import reverse
from django_tenants.test.cases import TenantTestCase


class TestByteDeckSummernoteSafeWidget(TenantTestCase):
    """ByteDeck's Summernote implementation, so called 'Safe' variant"""

    def test_widget(self):
        """Safe widget (iframe variant) input is "cleaned" to prevent XSS scripts from executing"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        widget = ByteDeckSummernoteSafeWidget()
        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})
        url = reverse("bytedeck_summernote-editor", kwargs={"id": "id_foobar"})

        assert url in html
        assert 'id="id_foobar"' in html

        illegal_tags = '<script>alert("Hello")</script>'
        value = widget.value_from_datadict({"foobar": illegal_tags}, {}, "foobar")

        self.assertEqual(value, '&lt;script&gt;alert("Hello")&lt;/script&gt;')

    def test_widget_inplace(self):
        """Safe widget (non-iframe aka inplace variant) input is "cleaned" to prevent XSS scripts from executing"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeInplaceWidget

        widget = ByteDeckSummernoteSafeInplaceWidget()

        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})

        assert "summernote" in html

        illegal_tags = '<script>alert("Hello")</script>'
        value = widget.value_from_datadict({"foobar": illegal_tags}, {}, "foobar")

        self.assertEqual(value, '&lt;script&gt;alert("Hello")&lt;/script&gt;')

    def test_config_codeview_filter(self):
        """Safe widget (iframe variant) configured to prevent XSS scripts from executing"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        widget = ByteDeckSummernoteSafeWidget()
        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})

        assert '"codeviewFilter": true' in html


class TestByteDeckSummernoteAdvancedWidget(TenantTestCase):
    """ByteDeck's Summernote implementation, so called 'Advanced' variant"""

    def test_widget(self):
        """Advanced widget (iframe variant) input is preserved "as-is", no sanitization is done"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        widget = ByteDeckSummernoteAdvancedWidget()
        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})
        url = reverse("bytedeck_summernote-editor", kwargs={"id": "id_foobar"})

        assert url in html
        assert 'id="id_foobar"' in html

        illegal_tags = '<script>alert("Hello")</script>'
        value = widget.value_from_datadict({"foobar": illegal_tags}, {}, "foobar")

        self.assertEqual(value, '<script>alert("Hello")</script>')

    def test_widget_inplace(self):
        """Advanced widget (non-iframe aka inplace variant) input is preserved "as-is", no sanitization is done"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedInplaceWidget

        widget = ByteDeckSummernoteAdvancedInplaceWidget()

        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})

        assert "summernote" in html

        illegal_tags = '<script>alert("Hello")</script>'
        value = widget.value_from_datadict({"foobar": illegal_tags}, {}, "foobar")

        self.assertEqual(value, '<script>alert("Hello")</script>')

    def test_config_codeview_filter(self):
        """Advanced widget (iframe variant) configured to disable XSS protection"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        widget = ByteDeckSummernoteAdvancedWidget()
        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})

        assert '"codeviewFilter": false' in html
