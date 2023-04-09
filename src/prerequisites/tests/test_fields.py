from django_tenants.test.cases import TenantTestCase

from prerequisites.models import IsAPrereqMixin


class PrereqContentObjectChoiceFieldTest(TenantTestCase):

    def test_hardcoded_prereq_model_choice(self):
        """If this test fails, then probably means a new model implements `IsAPrereqMixin`, or a model was removed."""
        from prerequisites.forms import PrereqContentObjectChoiceField

        expected_list = IsAPrereqMixin.all_registered_model_classes()

        f = PrereqContentObjectChoiceField()

        self.assertEqual([qs.model for qs in f.queryset.get_querysets()], expected_list)
