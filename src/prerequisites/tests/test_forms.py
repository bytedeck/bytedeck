from django_tenants.test.cases import TenantTestCase

from prerequisites.models import IsAPrereqMixin
from prerequisites.forms import hardcoded_prereq_model_choice


class PrereqFormsTest(TenantTestCase):

    def generate_prereq_model_choice(): 
        """ A list of tuples: [(model, model_search_field), ...] for DAL widgets"""
        models = IsAPrereqMixin.all_registered_model_classes()
        model_choices = [(model, model.dal_autocomplete_search_fields()) for model in models]
        print([(model.__name__, model.dal_autocomplete_search_fields()) for model in models])
        return model_choices

    def test_hardcoded_prereq_model_choice(self):
        """If this test fails, then probably means a new model implements `IsAPrereqMixin`, or a model was removed.
        
        The `hardcoded_prereq_model_choice()` method should return a list of tuples that matches
        the [(model1, 'search_field1'), (model2, 'search_field2'), ...] for every model that 
        implements the `IsAPrereqMixin`.       
 
        """
        hardcoded_list = hardcoded_prereq_model_choice()
        expected_list = PrereqFormsTest.generate_prereq_model_choice()

        self.assertEqual(hardcoded_list, expected_list)
