from django.contrib.contenttypes.models import ContentType

from django_tenants.test.cases import TenantTestCase
from queryset_sequence import QuerySetSequence

from djcytoscape.models import CytoScape


class CytoscapeGFKChoiceFieldTest(TenantTestCase):

    def test_queryset(self):
        """ Quick test to see if the hardcoded model list is equal to CytoScape.ALLOWED_INITIAL_CONTENT_TYPES """
        from djcytoscape.forms import CytoscapeGFKChoiceField

        dynamically_loaded_models = [
            ct.model_class() for ct in ContentType.objects.filter(CytoScape.ALLOWED_INITIAL_CONTENT_TYPES)]

        f = CytoscapeGFKChoiceField()

        self.assertEqual(dynamically_loaded_models, [qs.model for qs in f.queryset.get_querysets()])

    def test_overridden_querysetsequence(self):
        """ Quick test to see if the overridden_querysetsence method does custom filtering or not """
        from djcytoscape.forms import CytoscapeGFKChoiceField

        dynamically_loaded_models = [
            ct.model_class() for ct in ContentType.objects.filter(CytoScape.ALLOWED_INITIAL_CONTENT_TYPES)]

        f = CytoscapeGFKChoiceField()

        # default QuerySetSequence includes all objects
        querysetsequence = QuerySetSequence(*[x.objects.all() for x in dynamically_loaded_models])

        # get first object of first allowed initial content types and use it as "initial_object"
        content_type = ContentType.objects.filter(CytoScape.ALLOWED_INITIAL_CONTENT_TYPES).first()
        initial_object = content_type.model_class().objects.first()

        # initial_object is *not* in use, should be *included* in querysetsequence
        self.assertIn(initial_object, [
            o for qs in f.overridden_querysetsequence(querysetsequence).get_querysets() for o in qs])

        # generate new map using "initial_object" object
        CytoScape.generate_map(initial_object, "test")

        # initial_object is *already* in use, should be *excluded* from querysetsequence
        self.assertNotIn(initial_object, [
            o for qs in f.overridden_querysetsequence(querysetsequence).get_querysets() for o in qs])
