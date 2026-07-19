import json
import random
import string
import collections

from django import forms
from django.db.models import Q
from django.core import signing
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from django_tenants.test.client import TenantClient
from queryset_sequence import QuerySetSequence

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from utilities.fields import GFKChoiceField
from utilities.widgets import GFKSelect2Widget
from quest_manager.models import Quest


def random_string(n):
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(n)
    )


class CustomGFKSelect2Widget(GFKSelect2Widget):
    queryset = QuerySetSequence(Group.objects.all())
    search_fields = {
        'auth': {'group': ['name__icontains']},
    }

    def label_from_instance(self, obj):
        return str(obj.name).upper()


class GFKSelect2WidgetForm(forms.Form):
    f = GFKChoiceField(
        queryset=QuerySetSequence(
            Group.objects.all(),
        ),
        required=False,
        widget=CustomGFKSelect2Widget(),
    )


class TestGFKSelect2Widget(ByteDeckTenantTestCase):
    form = GFKSelect2WidgetForm(initial={'f': '1-1'})

    @classmethod
    def setUpTestData(cls):
        """Create 100 groups for the widget to render and filter over."""
        cls.groups = Group.objects.bulk_create(
            [Group(pk=pk, name=random_string(50)) for pk in range(100)]
        )

    def setUp(self):
        """Build a tenant-aware test client."""
        self.client = TenantClient(self.tenant)

    def _ct_pk(self, obj):
        return f'{ContentType.objects.get_for_model(obj).pk}-{obj.pk}'

    def test_widget__renders_initial_data(self):
        """Widget renders the initial GFK value's string in the form output."""
        group = self.groups[0]
        form = self.form.__class__(initial={'f': group})
        assert str(group) in form.as_p()

    def test_label_from_instance__initial(self):
        """Custom label_from_instance is applied to the initial value's rendered label."""
        group = self.groups[0]
        group.name = group.name.lower()
        group.save()

        form = self.form.__class__(initial={'f': group})
        assert group.name not in form.as_p(), form.as_p()
        assert group.name.upper() in form.as_p()

    def test_selected_option__marked_selected(self):
        """Rendered output marks the chosen value as selected and leaves others unselected."""
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

    def test_selected_option__label_from_instance(self):
        """The selected option's label reflects the custom label_from_instance transform."""
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

    def test_get_queryset__raises_without_queryset(self):
        """get_queryset raises NotImplementedError until a queryset is assigned."""
        widget = GFKSelect2Widget()
        with self.assertRaises(NotImplementedError):
            widget.get_queryset()
        widget.queryset = QuerySetSequence(Group.objects.all())
        assert isinstance(widget.get_queryset(), QuerySetSequence)

    def test_get_search_fields__raises_without_config(self):
        """get_search_fields raises NotImplementedError until search_fields is configured."""
        widget = GFKSelect2Widget()
        with self.assertRaises(NotImplementedError):
            widget.get_search_fields(Group)

        widget.search_fields = {'auth': {'group': ['name__icontains']}}
        assert isinstance(widget.get_search_fields(Group), collections.abc.Iterable)
        assert all(isinstance(x, str) for x in widget.get_search_fields(Group))

    def test_filter_queryset__matches_search_term(self):
        """filter_queryset returns results matching a full or space-split search term."""
        widget = CustomGFKSelect2Widget()
        assert widget.filter_queryset(None, self.groups[0].name[:3]).exists()

        widget = CustomGFKSelect2Widget()
        qs = widget.filter_queryset(None, " ".join([self.groups[0].name[:3], self.groups[0].name[3:]]))
        assert qs.exists()

    def test_filter_queryset__queryset_kwarg(self):
        """A queryset passed via kwarg is searchable through filter_queryset."""
        widget = GFKSelect2Widget(
            queryset=QuerySetSequence(Group.objects.all()), search_fields={'auth': {'group': ['name__icontains']}})
        group = Group.objects.last()
        result = widget.filter_queryset(None, group.name)
        assert result.exists()

    def test_filter_queryset__respects_queryset_constraints(self):
        """filter_queryset honors the underlying queryset's include/exclude constraints."""
        group = self.groups[0]

        queryset = QuerySetSequence(Group.objects.filter(~Q(name__icontains=group.name)))
        widget = GFKSelect2Widget(
            queryset=queryset, search_fields={'auth': {'group': ['name__icontains']}})
        result = widget.filter_queryset(None, group.name)
        assert not result.exists()

        queryset = QuerySetSequence(Group.objects.filter(Q(name__icontains=group.name)))
        widget = GFKSelect2Widget(
            queryset=queryset, search_fields={'auth': {'group': ['name__icontains']}})
        result = widget.filter_queryset(None, group.name)
        assert result.exists()

    def test_render__registers_ajax_view(self):
        """Rendering the widget registers it so the AJAX endpoint returns its results."""
        widget = GFKSelect2Widget(
            queryset=QuerySetSequence(Group.objects.all()), search_fields={'auth': {'group': ['name__icontains']}})
        widget.render('name', '1-1')
        url = reverse('utilities:querysetsequence_auto-json')
        group = Group.objects.last()
        data = {
            'field_id': signing.dumps(widget.uuid),
            'term': group.name
        }
        response = self.client.get(url, data=data)
        assert response.status_code == 200, response.content
        data = json.loads(response.content.decode('utf-8'))
        assert data['results']
        assert self._ct_pk(group) in [result['id'] for result in data['results'][0]['children']]

    def test_render__caches_widget_config(self):
        """Rendering caches the widget's max_results, search_fields, and queryset."""
        from django_select2.cache import cache

        widget = GFKSelect2Widget(
            queryset=QuerySetSequence(Group.objects.all()), search_fields={'auth': {'group': ['name__icontains']}})
        widget.render('name', '1-1')
        cached_widget = cache.get(widget._get_cache_key())
        assert cached_widget['max_results'] == widget.max_results
        assert dict(cached_widget['search_fields']) == widget.search_fields
        qs = widget.get_queryset()
        assert isinstance(cached_widget['queryset'][0][0], qs.get_querysets()[0].__class__)
        assert str(cached_widget['queryset'][0][1]) == str(qs.get_querysets()[0].query)

    def test_get_url__returns_string(self):
        """get_url returns the AJAX endpoint URL as a string."""
        widget = GFKSelect2Widget(
            queryset=QuerySetSequence(Group.objects.all()), search_fields={'auth': {'group': ['name__icontains']}})
        assert isinstance(widget.get_url(), str)

    def test_get_queryset__preserves_id_ordering(self):
        """ Tests if there isn't any unexpected ordering issues when getting the queryset. """
        queryset_random = Quest.objects.order_by('name')
        queryset_expected = queryset_random.order_by('id')

        widget = GFKSelect2Widget(
            queryset=QuerySetSequence(queryset_random),
            search_fields={'quest_manager': {'quest': ['name__icontains']}}
        )

        self.assertQuerySetEqual(widget.get_queryset(), queryset_expected)
        self.assertQuerySetEqual(widget.filter_queryset(None, ''), queryset_expected)
