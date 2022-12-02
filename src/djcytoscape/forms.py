from django import forms

from django_select2.forms import Select2Widget
from queryset_sequence import QuerySetSequence

from utilities.forms import FutureModelForm
from utilities.fields import ContentObjectChoiceField

from .models import CytoScape


def get_model_options():
    """
        provides ContentTypes that are part of CytoScape.ALLOWED_INITIAL_CONTENT_TYPES
        formatted for utilities.fields.ContentObjectModelField use
        from prerequisites.forms:
            Can't always dynamically load this list due to accessing contenttypes too early
            So instead provide a hard coded list which is checked during testing to ensure it matches
            what the dynamically loaded list would have produced
    """
    from quest_manager.models import Quest
    from badges.models import Badge
    from courses.models import Rank

    return [Quest, Rank, Badge]


class GenerateQuestMapForm(FutureModelForm):

    class Meta:
        model = CytoScape
        fields = [
            'name',
            'initial_content_object',
            'parent_scape',
        ]

    name = forms.CharField(max_length=50, required=False, help_text="If not provided, the initial quest's name will be used")
    
    initial_content_object = ContentObjectChoiceField(
        label='Initial Object',
        required=True,
        queryset=QuerySetSequence(*[klass.objects.all() for klass in get_model_options()]),
        widget=Select2Widget,
    )

    parent_scape = forms.ModelChoiceField(
        label='Parent Quest Map', 
        required=False,
        queryset=CytoScape.objects.all(),
    )

    def __init__(self, *args, **kwargs):
        self.autobreak = kwargs.pop('autobreak', None)
        super().__init__(*args, **kwargs)

        self.fields['initial_content_object'].widget.attrs['data-placeholder'] = 'Type to search'

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
