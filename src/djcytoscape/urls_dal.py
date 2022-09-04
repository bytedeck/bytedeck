from djcytoscape.forms import GenerateQuestMapForm

""" 
    this is necessary since dal autocomplete.Select2GenericForeignKeyModelField calls its reverse urls without namespaces in mind

    so when putting GenerateQuestMapForm.as_urls() in djcytoscape.urls it would appear as:
    >> 'djcytoscape:generate_quest_map_form_url_14312347247'
    instead of (which Select2GenericForeignKeyModelField widget would use):
    >> 'generate_quest_map_form_url_14312347247'

    since
    >> 'djcytoscape:generate_quest_map_form_url_14312347247' != 'generate_quest_map_form_url_14312347247'
    you will get a NoReverseMatch error

    for more info check comments
    https://stackoverflow.com/questions/72588677/django-autocomplete-light-generic-foreign-key-invalid-view-function
"""

urlpatterns = []
urlpatterns.extend(GenerateQuestMapForm.as_urls())
