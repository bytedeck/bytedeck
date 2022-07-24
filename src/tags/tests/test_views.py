from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from django.contrib.auth import get_user_model

from model_bakery import baker
from taggit.models import Tag
from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


class TagAutocompleteViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)
        Tag.objects.create(name="test-tag")

    def test_autocomplete_view(self):
        """ Make sure django-autocomplete-light view for tag autocomplete widget is accessible"""
        response = self.client.get(reverse('tags:autocomplete'))

        self.assertEqual(response.status_code, 200)

    def test_autocomplete_view__unauthenticated(self):
        """ The view should return an empty json response if the user is not authenticated """
        self.client.logout()
        response = self.client.get(reverse('tags:autocomplete'))
        self.assertEqual(response.json()['results'], [])

    def test_autocomplete_view__authenticated(self):
        """ The view should return tags in json results if the user is authenticated """
        self.client.force_login(baker.make('User'))
        response = self.client.get(reverse('tags:autocomplete'))
        json_results = response.json()['results']
        self.assertEqual(len(json_results), 1)
        self.assertEqual(json_results[0]['text'], 'test-tag')
