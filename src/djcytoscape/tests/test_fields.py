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

    def test_queryset_objects_was_excluded(self):
        """ Test to see if objects "in use" are being excluded from queryset"""
        from djcytoscape.forms import CytoscapeGFKChoiceField

        # get first object of first allowed initial content types and use it as "initial_object"
        content_type = ContentType.objects.filter(CytoScape.ALLOWED_INITIAL_CONTENT_TYPES).first()
        initial_object = content_type.model_class().objects.first()

        # Calling the CytoscapeGFKChoiceField() class constructor creates, initializes
        # and returns a new instance of the class.
        #
        # First, Python calls .__new__() and then .__init__(), resulting in a new and fully
        # initialized intance of CytoscapeGFKChoiceField.
        f = CytoscapeGFKChoiceField()
        # initial_object is *not* in use, should be *included* in queryset
        self.assertIn(initial_object, [o for qs in f.queryset.get_querysets() for o in qs])

        # generate new map using "initial_object" object
        CytoScape.generate_map(initial_object, "test")

        # call the class to construct an object (again)
        f = CytoscapeGFKChoiceField()
        # initial_object is *already* in use, should be *excluded* from queryset
        self.assertNotIn(initial_object, [o for qs in f.queryset.get_querysets() for o in qs])
