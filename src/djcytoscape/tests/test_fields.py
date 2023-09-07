from django.contrib.contenttypes.models import ContentType

from django_tenants.test.cases import TenantTestCase

from djcytoscape.models import CytoScape


class CytoscapeGFKChoiceFieldTest(TenantTestCase):

    def test_queryset(self):
        """ Quick test to see if the hardcoded model list is equal to CytoScape.ALLOWED_INITIAL_CONTENT_TYPES """
        from djcytoscape.forms import CytoscapeGFKChoiceField

        dynamically_loaded_models = [
            ct.model_class() for ct in ContentType.objects.filter(CytoScape.ALLOWED_INITIAL_CONTENT_TYPES)]

        f = CytoscapeGFKChoiceField()

        self.assertEqual(dynamically_loaded_models, [qs.model for qs in f.queryset.get_querysets()])

    def test_queryset_is_filterable(self):
        from djcytoscape.forms import CytoscapeGFKChoiceField

        content_type = ContentType.objects.filter(CytoScape.ALLOWED_INITIAL_CONTENT_TYPES).first()
        obj = content_type.model_class().objects.first()

        f = CytoscapeGFKChoiceField()
        self.assertIn(obj, [o for qs in f.queryset.get_querysets() for o in qs])

        CytoScape.generate_map(obj, "test")

        f = CytoscapeGFKChoiceField()
        self.assertNotIn(obj, [o for qs in f.queryset.get_querysets() for o in qs])
