from django import forms
from django.contrib.contenttypes.models import ContentType
from djcytoscape.models import CytoScape


class GenerateQuestMapForm(forms.Form):

    content_types = ContentType.objects.filter(CytoScape.ALLOWED_INITIAL_CONTENT_TYPES)
    scapes = CytoScape.objects.all()

    name = forms.CharField(max_length=50, required=False,
                           help_text="If not provided, the initial quest's name will be used")
    initial_content_type = forms.ModelChoiceField(queryset=content_types, label='Initial Object Type', required=True)
    initial_object_id = forms.IntegerField(required=True, label='Initial Object ID')
    scape = forms.ModelChoiceField(queryset=scapes, label='Parent Quest Map', required=False)
