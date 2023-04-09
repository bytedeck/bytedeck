from django.contrib.contenttypes.models import ContentType

from django_tenants.test.cases import TenantTestCase

from djcytoscape.models import CytoScape


class CytoscapeGFKChoiceFieldTest(TenantTestCase):

    def test_queryset(self):
        from djcytoscape.forms import CytoscapeGFKChoiceField

        """ Quick test to see if the hardcoded model list is equal to CytoScape.ALLOWED_INITIAL_CONTENT_TYPES """
        dynamically_loaded_models = [
            ct.model_class() for ct in ContentType.objects.filter(CytoScape.ALLOWED_INITIAL_CONTENT_TYPES)]

        f = CytoscapeGFKChoiceField()

        self.assertEqual(dynamically_loaded_models, [qs.model for qs in f.queryset.get_querysets()])
