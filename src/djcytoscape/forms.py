from django import forms
from djcytoscape.models import CytoScape
from quest_manager.models import Quest


class GenerateQuestMapForm(forms.Form):
    quests = Quest.objects.all()
    scapes = CytoScape.objects.all()
    name = forms.CharField(max_length=50, required=False,
                           help_text="If not provided, the initial quest's name will be used")
    quest = forms.ModelChoiceField(queryset=quests, label='Initial Quest', required=True)
    scape = forms.ModelChoiceField(queryset=scapes, label='Parent Quest Map', required=False)
