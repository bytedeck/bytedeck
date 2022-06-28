from django.urls import reverse

from django_tenants.test.cases import TenantTestCase


class PrereqAutocompleteViewTest(TenantTestCase):
    def setUp(self):
        pass

    def test_PrereqContentTypeAutocomplete(self):
        """
        Ensure the view's url can be reversed
        https://django-autocomplete-light.readthedocs.io/en/master/tutorial.html#register-the-autocomplete-view
        """
        
        self.assertEqual(reverse('prereq-ct-autocomplete'), "/prerequisites/autocomplete/ct/")
