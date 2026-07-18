from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from prerequisites.models import IsAPrereqMixin


class PrereqGFKChoiceFieldTest(ByteDeckTenantTestCase):

    def test_hardcoded_prereq_model_choice(self):
        """If this test fails, then probably means a new model implements `IsAPrereqMixin`, or a model was removed."""
        from prerequisites.forms import PrereqGFKChoiceField

        expected_list = IsAPrereqMixin.all_registered_model_classes()

        f = PrereqGFKChoiceField()

        self.assertEqual([qs.model for qs in f.queryset.get_querysets()], expected_list)
