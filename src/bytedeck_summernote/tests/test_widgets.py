from django import forms
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase


class TestByteDeckSummernoteWidget(TenantTestCase):
    def test_widget(self):
        """Widget injects custom URL into HTML template"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        widget = ByteDeckSummernoteAdvancedWidget()
        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})
        url = reverse("bytedeck_summernote-editor", kwargs={"id": "id_foobar"})

        assert url in html
        assert 'id="id_foobar"' in html

    def test_widget_inplace(self):
        """Input is "cleaned" to prevent XSS scripts from executing"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        widget = ByteDeckSummernoteSafeWidget()

        html = widget.render("foobar", "lorem ipsum", attrs={"id": "id_foobar"})

        assert "summernote" in html

        illegal_tags = '<script>alert("Hello")</script>'
        value = widget.value_from_datadict({"foobar": illegal_tags}, {}, "foobar")

        self.assertEqual(value, '&lt;script&gt;alert("Hello")&lt;/script&gt;')

    def test_empty(self):
        """Input is "cleaned" from an empty HTML tags"""
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        class SimpleForm(forms.Form):
            foobar = forms.CharField(widget=ByteDeckSummernoteSafeWidget())

        should_be_parsed_as_empty = "<p><br></p>"
        should_not_be_parsed_as_empty = "<p>lorem ipsum</p>"

        f = SimpleForm({"foobar": should_be_parsed_as_empty})
        assert not f.is_valid()
        assert not f.cleaned_data.get("foobar")

        f = SimpleForm({"foobar": should_not_be_parsed_as_empty})
        assert f.is_valid()
        assert f.cleaned_data.get("foobar")
