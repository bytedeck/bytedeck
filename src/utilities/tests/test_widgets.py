import json
import random
import string
import collections

from django import forms
from django.core import signing
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.utils.six import text_type
from django.urls import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from queryset_sequence import QuerySetSequence

from utilities.fields import ContentObjectChoiceField
from utilities.widgets import ContentObjectSelect2Widget


def random_string(n):
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(n)
    )


class CustomContentObjectSelect2Widget(ContentObjectSelect2Widget):
    queryset = QuerySetSequence(Group.objects.all())
    search_fields = [
        'name__icontains'
    ]

    def label_from_instance(self, obj):
        return str(obj.name).upper()


class ContentObjectsSelect2WidgetForm(forms.Form):
    f = ContentObjectChoiceField(
        queryset=QuerySetSequence(
            Group.objects.all(),
        ),
        required=False,
        widget=CustomContentObjectSelect2Widget(),
    )


class TestContentObjectSelect2Widget(TenantTestCase):
    form = ContentObjectsSelect2WidgetForm(initial={'f': '1-1'})

    def setUp(self):
        self.client = TenantClient(self.tenant)

        self.groups = Group.objects.bulk_create(
            [Group(pk=pk, name=random_string(50)) for pk in range(100)]
        )

    def _ct_pk(self, obj):
        return '{}-{}'.format(ContentType.objects.get_for_model(obj).pk, obj.pk)

    def test_initial_data(self):
        group = self.groups[0]
        form = self.form.__class__(initial={'f': group})
        assert text_type(group) in form.as_p()

    def test_label_from_instance_initial(self):
        group = self.groups[0]
        group.name = group.name.lower()
        group.save()

        form = self.form.__class__(initial={'f': group})
        assert group.name not in form.as_p(), form.as_p()
        assert group.name.upper() in form.as_p()

    def test_selected_option(self):
        group = self.groups[0]
        another_group = self.groups[1]
        not_required_field = self.form.fields['f']
        assert not_required_field.required is False
        widget_output = not_required_field.widget.render(
            'f', self._ct_pk(group))
        selected_option = '<option value="{ct_pk}" selected="selected">{value}</option>'.format(
            ct_pk=self._ct_pk(group), value=str(group))
        selected_option_a = '<option value="{ct_pk}" selected>{value}</option>'.format(
            ct_pk=self._ct_pk(group), value=str(group))
        unselected_option = '<option value="{ct_pk}">{value}</option>'.format(
            ct_pk=self._ct_pk(another_group), value=str(another_group))

        assert selected_option in widget_output or selected_option_a in widget_output, widget_output
        assert unselected_option not in widget_output

    def test_selected_option_label_from_instance(self):
        group = self.groups[0]
        group.name = group.name.lower()
        group.save()

        field = self.form.fields['f']
        widget_output = field.widget.render('f', self._ct_pk(group))

        def get_selected_options(group):
            return '<option value="{ct_pk}" selected="selected">{value}</option>'.format(
                ct_pk=self._ct_pk(group), value=str(group)), '<option value="{ct_pk}" selected>{value}</option>'.format(
                ct_pk=self._ct_pk(group), value=str(group))

        assert all(o not in widget_output for o in get_selected_options(group))
        group.name = group.name.upper()

        assert any(o in widget_output for o in get_selected_options(group))

    def test_get_queryset(self):
        widget = ContentObjectSelect2Widget()
        with self.assertRaises(NotImplementedError):
            widget.get_queryset()
        widget.queryset = QuerySetSequence(Group.objects.all())
        assert isinstance(widget.get_queryset(), QuerySetSequence)

    def test_get_search_fields(self):
        widget = ContentObjectSelect2Widget()
        with self.assertRaises(NotImplementedError):
            widget.get_search_fields()

        widget.search_fields = ['name__icontains']
        assert isinstance(widget.get_search_fields(), collections.Iterable)
        assert all(isinstance(x, text_type) for x in widget.get_search_fields())

    def test_filter_queryset(self):
        widget = CustomContentObjectSelect2Widget()
        assert widget.filter_queryset(self.groups[0].name[:3]).exists()

        widget = CustomContentObjectSelect2Widget()
        qs = widget.filter_queryset(" ".join([self.groups[0].name[:3], self.groups[0].name[3:]]))
        assert qs.exists()

    def test_queryset_kwarg(self):
        widget = ContentObjectSelect2Widget(
            queryset=QuerySetSequence(Group.objects.all()), search_fields=['name__icontains'])
        group = Group.objects.last()
        result = widget.filter_queryset(group.name)
        assert result.exists()

    def test_ajax_view_registration(self):
        widget = ContentObjectSelect2Widget(
            queryset=QuerySetSequence(Group.objects.all()), search_fields=['name__icontains'])
        widget.render('name', '1-1')
        url = reverse('utilities:querysetsequence_auto-json')
        group = Group.objects.last()
        response = self.client.get(url, data=dict(field_id=signing.dumps(id(widget)), term=group.name))
        assert response.status_code == 200, response.content
        data = json.loads(response.content.decode('utf-8'))
        assert data['results']
        assert self._ct_pk(group) in [result['id'] for result in data['results'][0]['children']]

    def test_render(self):
        from django_select2.cache import cache

        widget = ContentObjectSelect2Widget(
            queryset=QuerySetSequence(Group.objects.all()), search_fields=['name__icontains'])
        widget.render('name', '1-1')
        cached_widget = cache.get(widget._get_cache_key())
        assert cached_widget['max_results'] == widget.max_results
        assert list(cached_widget['search_fields']) == widget.search_fields
        qs = widget.get_queryset()
        assert isinstance(cached_widget['queryset'][0][0], qs.get_querysets()[0].__class__)
        assert text_type(cached_widget['queryset'][0][1]) == text_type(qs.get_querysets()[0].query)

    def test_get_url(self):
        widget = ContentObjectSelect2Widget(
            queryset=QuerySetSequence(Group.objects.all()), search_fields=['name__icontains'])
        assert isinstance(widget.get_url(), text_type)
