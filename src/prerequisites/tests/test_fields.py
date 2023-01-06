from django_tenants.test.cases import TenantTestCase

from prerequisites.models import IsAPrereqMixin
from prerequisites.forms import AllowedContentObjectChoiceField


class AllowedContentObjectChoiceFieldTest(TenantTestCase):

    def test_hardcoded_prereq_model_choice(self):
        """If this test fails, then probably means a new model implements `IsAPrereqMixin`, or a model was removed."""
        expected_list = IsAPrereqMixin.all_registered_model_classes()

        f = AllowedContentObjectChoiceField()

        self.assertEqual([qs.model for qs in f.queryset.get_querysets()], expected_list)
