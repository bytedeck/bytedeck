from django.urls import reverse

from django_tenants.test.cases import TenantTestCase


class TestByteDeckSummernoteWidget(TenantTestCase):

    def test_widget(self):
        from bytedeck_summernote.widgets import ByteDeckSummernoteAdvancedWidget

        widget = ByteDeckSummernoteAdvancedWidget()
        html = widget.render(
            'foobar', 'lorem ipsum', attrs={'id': 'id_foobar'}
        )
        url = reverse('bytedeck_summernote-editor', kwargs={'id': 'id_foobar'})

        assert url in html
        assert 'id="id_foobar"' in html

    def test_widget_inplace(self):
        from bytedeck_summernote.widgets import ByteDeckSummernoteSafeWidget

        widget = ByteDeckSummernoteSafeWidget()

        html = widget.render(
            'foobar', 'lorem ipsum', attrs={'id': 'id_foobar'}
        )

        assert 'summernote' in html

        illegal_tags = '<script>alert("Hello")</script>'
        value = widget.value_from_datadict({"foobar": illegal_tags}, {}, "foobar")

        self.assertEqual(value, '&lt;script&gt;alert("Hello")&lt;/script&gt;')
