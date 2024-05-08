import copy
import operator
from functools import reduce

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from django_select2.forms import HeavySelect2Widget
from queryset_sequence import QuerySetSequence


class GFKSelect2Mixin:
    queryset = None
    search_fields = {}
    """
    Model lookups that are used to filter the QuerySetSequence.

    Example::
        search_fields = {
            'myapp': {'mymodel': ['title__icontains']}
        }
    """

    max_results = 25

    @property
    def empty_label(self):
        from utilities.fields import GFKChoiceIterator

        if isinstance(self.choices, GFKChoiceIterator):
            return self.choices.field.empty_label
        return ''

    def __init__(self, *args, **kwargs):
        self.queryset = kwargs.pop('queryset', self.queryset)
        self.search_fields = kwargs.pop('search_fields', self.search_fields)
        self.max_results = kwargs.pop('max_results', self.max_results)
        defaults = {'data_view': 'utilities:querysetsequence_auto-json'}
        defaults.update(kwargs)
        super().__init__(*args, **defaults)

    def set_to_cache(self):
        """
        Add widget's attributes to Django's cache.

        Split the QuerySetSequence, to not pickle the result set.

        """
        from django_select2.cache import cache

        queryset = self.get_queryset()
        cache.set(
            self._get_cache_key(),
            {
                'queryset': [(qs.none(), qs.query) for qs in queryset.get_querysets()],
                'cls': self.__class__,
                'search_fields': dict(self.search_fields),
                'max_results': int(self.max_results),
                'url': str(self.get_url()),
                'dependent_fields': {},  # not implemented
            },
        )

    def get_search_fields(self, model):
        """Return list of lookup names."""
        if self.search_fields:
            return self.search_fields[model._meta.app_label][model._meta.model_name]
        raise NotImplementedError(
            '%s, must implement "search_fields".' % self.__class__.__name__
        )

    def filter_queryset(self, term, queryset=None, **dependent_fields):
        """
        Return QuerySetSequence filtered by search_fields matching the passed term.

        Args:
            term (str): Search term
            queryset (queryset_sequence.QuerySetSequence): QuerySetSequence to select choices from.

        Returns:
            QuerySetSequence: Filtered QuerySetSequence

        """
        if queryset is None:
            queryset = self.get_queryset()

        queryset_models = []
        for qs in queryset.get_querysets():
            model = qs.model

            select = Q()
            search_fields = self.get_search_fields(model)
            if search_fields and term:
                for bit in term.split():
                    or_queries = [Q(**{orm_lookup: bit}) for orm_lookup in search_fields]
                    select &= reduce(operator.or_, or_queries)
                or_queries = [Q(**{orm_lookup: term}) for orm_lookup in search_fields]
                select |= reduce(operator.or_, or_queries)

            queryset_models.append(qs.filter(select))

        # Aggregate querysets
        return QuerySetSequence(*queryset_models)

    def get_queryset(self):
        if self.queryset is not None:
            queryset = self.queryset
        elif hasattr(self.choices, 'queryset'):
            queryset = self.choices.queryset
        else:
            raise NotImplementedError(
                '%(cls)s is missing a QuerySet. Define '
                '%(cls)s.queryset, or override '
                '%(cls)s.get_queryset().' % {'cls': self.__class__.__name__}
            )
        return queryset

    def filter_choices_to_render(self, selected_choices):
        """Overwrite self.choices to exclude unselected values."""
        if len(selected_choices) == 1 and not selected_choices[0]:
            selected_choices = []

        ctype_models = {}

        for choice in selected_choices:
            ctype_pk, model_pk = choice.split('-', 1)
            ctype_pk = int(ctype_pk)
            ctype_models.setdefault(ctype_pk, [])
            ctype_models[ctype_pk].append(model_pk)

        self.choices = []
        ctype = ContentType.objects.get_for_id
        for ctype_pk, ids in ctype_models.items():
            results = ctype(ctype_pk).model_class().objects.filter(pk__in=ids)

            self.choices += [
                (f'{ctype_pk}-{r.pk}', self.label_from_instance(r))
                for r in results
            ]

    def optgroups(self, name, value, attrs=None):
        """
        Exclude unselected self.choices before calling the parent method.

        """
        # Filter out None values, not needed for autocomplete
        selected_choices = [str(c) for c in value if c]
        all_choices = copy.copy(self.choices)
        if self.get_url():
            self.filter_choices_to_render(selected_choices)
        elif not self.allow_multiple_selected:
            if self.attrs.get('data-placeholder'):
                self.choices.insert(0, (None, ''))
        result = super().optgroups(name, value, attrs)
        self.choices = all_choices
        return result

    def label_from_instance(self, obj):
        return str(obj)


class GFKSelect2Widget(GFKSelect2Mixin, HeavySelect2Widget):
    """
    Select2 drop in content object select widget.

    Example usage::

        class MyWidget(GFKSelect2Widget):
            search_fields = {
                'myapp': {'mymodel': ['title__icontains']}
            }

        class MyModelForm(FutureModelForm):
            my_field = GFKChoiceField(
                queryset=QuerySetSequence(...),
            )

            class Meta:
                model = MyModel
                fields = ('my_field', )
                widgets = {
                    'my_field': MyWidget,
                }

    or::

        class MyForm(forms.Form):
            my_choice = GFKChoiceField(
                queryset=QuerySetSequence(...),
                widget=GFKSelect2Widget(
                    search_fields={
                        'myapp': {'mymodel': ['title__icontains']}
                    }
                )
            )

    .. tip:: The GFKSelect2Widget will try
        to get the QuerySetSequence from the fields choices.
        Therefore you don't need to define a QuerySetSequence,
        if you just drop in the widget for a GFKChoiceField field.
    """
