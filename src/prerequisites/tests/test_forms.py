from django_tenants.test.cases import TenantTestCase

from prerequisites.models import IsAPrereqMixin
from prerequisites.forms import hardcoded_prereq_model_choice


class PrereqFormsTest(TenantTestCase):

    def generate_prereq_model_choice(): 
        return IsAPrereqMixin.all_registered_model_classes()

    def test_hardcoded_prereq_model_choice(self):
        """If this test fails, then probably means a new model implements `IsAPrereqMixin`, or a model was removed.
        
        The `hardcoded_prereq_model_choice()` method should return a list of models for every model that
        implements the `IsAPrereqMixin`.       
 
        """
        hardcoded_list = hardcoded_prereq_model_choice()
        expected_list = PrereqFormsTest.generate_prereq_model_choice()

        self.assertEqual(hardcoded_list, expected_list)
