from django import forms
from django.contrib.contenttypes.models import ContentType

from queryset_sequence import QuerySetSequence

from utilities.forms import FutureModelForm
from utilities.fields import AllowedGFKChoiceField

from .models import CytoScape


class CytoscapeGFKChoiceField(AllowedGFKChoiceField):
    """
    Provides ContentTypes that are part of CytoScape.ALLOWED_INITIAL_CONTENT_TYPES
    formatted for utilities.fields.AllowedGFKChoiceField use

    from prerequisites.forms:
        Can't always dynamically load this list due to accessing contenttypes too early
        So instead provide a hard coded list which is checked during testing to ensure it matches
        what the dynamically loaded list would have produced
    """

    def overridden_querysetsequence(self, querysetsequence: QuerySetSequence) -> QuerySetSequence:
        """Apply custom filtering and returns overridden QuerySetSequence instance"""
        queryset_models = []
        # get previously initialized "querysetsequence" and apply custom filtering
        for qs in querysetsequence.get_querysets():
            model = qs.model
            # do not use Quest, Rank or Badge as an initial object,
            # if it is already an intitial object for another map
            queryset_models.append(
                # use existing queryset, with all previously applied filtering and custom queries
                qs.exclude(
                    pk__in=CytoScape.objects.filter(
                        initial_content_type=ContentType.objects.get_for_model(model),
                    ).values_list('initial_object_id', flat=True)
                )
            )
        # aggregate querysets
        return QuerySetSequence(*queryset_models)

    def get_allowed_model_classes(self):
        model_classes = [
            ct.model_class() for ct in ContentType.objects.filter(
                CytoScape.ALLOWED_INITIAL_CONTENT_TYPES
            )
        ]
        return model_classes


class GenerateQuestMapForm(FutureModelForm):

    class Meta:
        model = CytoScape
        fields = [
            'name',
            'initial_content_object',
            'parent_scape',
        ]

    name = forms.CharField(max_length=50, required=False, help_text="If not provided, the initial quest's name will be used")

    initial_content_object = CytoscapeGFKChoiceField(label='Initial Object')

    parent_scape = forms.ModelChoiceField(
        label='Parent Quest Map',
        required=False,
        queryset=CytoScape.objects.all(),
    )

    def __init__(self, *args, **kwargs):
        self.autobreak = kwargs.pop('autobreak', None)
        super().__init__(*args, **kwargs)

    def save(self, **kwargs):
        obj = self.cleaned_data['initial_content_object']
        name = self.cleaned_data['name'] or str(obj)
        parent_scape = self.cleaned_data['parent_scape']

        return CytoScape.generate_map(initial_object=obj, name=name, parent_scape=parent_scape, autobreak=self.autobreak)


class QuestMapForm(GenerateQuestMapForm, forms.ModelForm):
    """  Only used when updating Cytoscape map"""

    class Meta(GenerateQuestMapForm.Meta):
        fields = [
            *GenerateQuestMapForm.Meta.fields,
            'is_the_primary_scape',
            'autobreak',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # prevent recursive maps
        self.fields['parent_scape'].queryset = self.fields['parent_scape'].queryset.exclude(id=self.instance.id)

    # save with ModelForm default instead of CytoScape.generate_map()
    def save(self, **kwargs):
        return super(forms.ModelForm, self).save(**kwargs)
