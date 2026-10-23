from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from prerequisites.models import IsAPrereqMixin


class PrereqGFKChoiceFieldTest(ByteDeckTenantTestCase):

    def test_queryset__matches_registered_prereq_models(self):
        """The field's queryset covers exactly the models registered via IsAPrereqMixin."""
        from prerequisites.forms import PrereqGFKChoiceField

        expected_list = IsAPrereqMixin.all_registered_model_classes()

        f = PrereqGFKChoiceField()

        self.assertEqual([qs.model for qs in f.queryset.get_querysets()], expected_list)
