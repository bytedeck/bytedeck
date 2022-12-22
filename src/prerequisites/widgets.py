from functools import reduce

from django.db.models import Q

from queryset_sequence import QuerySetSequence

from utilities.widgets import ContentObjectSelect2Widget


class CustomContentObjectSelect2Widget(ContentObjectSelect2Widget):

    def filter_queryset(self, term, queryset=None, **dependent_fields):
        """Return queryset."""
        if queryset is None:
            queryset = self.get_queryset()

        queryset_models = []
        for qs in queryset.get_querysets():
            model = qs.model
            if 'name' in [f.name for f in model._meta.get_fields()]:
                filter_value = 'name'
            elif 'title' in [f.name for f in model._meta.get_fields()]:
                filter_value = 'title'

            kwargs_model = {
                '{}__icontains'.format(filter_value): term if term else ''
            }
            forward_filtered = [Q(**kwargs_model)]

            # link the different field by an & query
            and_forward_filtered = reduce(lambda x, y: x & y, forward_filtered)

            queryset_models.append(model.objects.filter(and_forward_filtered))

        # Aggregate querysets
        return QuerySetSequence(*queryset_models)
