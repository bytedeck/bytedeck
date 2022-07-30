from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from django.contrib.auth import get_user_model

from model_bakery import baker
from taggit.models import Tag
from tags.forms import TagForm
from hackerspace_online.tests.utils import ViewTestUtilsMixin, generate_form_data

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


class TagCRUDViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        self.test_password = "password"
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student = User.objects.create_user('test_student', password=self.test_password)

        self.tag = Tag.objects.create(name="test-tag")

    def test_page_status_code__anonymous(self):
        """Make sure the all views are not accessible to anonymous users"""
        self.assert302('tags:list')
        self.assert302('tags:detail', args=[self.tag.pk])
        self.assertRedirectsAdmin('tags:create')
        self.assertRedirectsAdmin('tags:update', args=[self.tag.pk])
        self.assertRedirectsAdmin('tags:delete', args=[self.tag.pk])

    def test_page_status_code__student(self):
        """Make sure the list/detail views are accessible students but create/update/delete are not"""
        self.client.force_login(self.test_student)

        self.assert200('tags:list')
        self.assert200('tags:detail', args=[self.tag.pk])
        self.assertRedirectsAdmin('tags:create')
        self.assertRedirectsAdmin('tags:update', args=[self.tag.pk])
        self.assertRedirectsAdmin('tags:delete', args=[self.tag.pk])

    def test_page_status_code__teacher(self):
        """Make sure the everything is accessible to teachers"""
        self.client.force_login(self.test_teacher)
        
        self.assert200('tags:list')
        self.assert200('tags:detail', args=[self.tag.pk])
        self.assert200('tags:create')
        self.assert200('tags:update', args=[self.tag.pk])
        self.assert200('tags:delete', args=[self.tag.pk])

    def test_ListView(self):
        """Make sure list view displays all tags correctly"""
        baker.make(Tag, _quantity=5)
        
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('tags:list'))

        object_list = response.context['object_list']

        self.assertEqual(Tag.objects.count(), len(object_list))
        
        for model_obj, ctx_obj in zip(Tag.objects.all(), object_list):
            self.assertEqual(model_obj.pk, ctx_obj.pk)

    def test_ListView__admin_buttons_staff(self):
        """Make sure admin buttons in list view show up for staff"""
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('tags:list'))

        self.assertContains(response, reverse('tags:update', args=[self.tag.pk]))
        self.assertContains(response, reverse('tags:delete', args=[self.tag.pk]))

    def test_ListView__admin_buttons_student(self):
        """Make sure admin buttons in list view dont show up for student"""
        self.client.force_login(self.test_student)
        response = self.client.get(reverse('tags:list'))

        self.assertNotContains(response, reverse('tags:update', args=[self.tag.pk]))
        self.assertNotContains(response, reverse('tags:delete', args=[self.tag.pk]))

    def test_DetailView(self):
        """Make sure detail view displays related quest/badges correctly"""
        quest = baker.make('quest_manager.quest')
        badge = baker.make('badges.badge')
        quest.tags.add(self.tag.name)
        badge.tags.add(self.tag.name)

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('tags:detail', args=[self.tag.pk]))

        self.assertContains(response, quest.name)
        self.assertContains(response, badge.name)

    def test_CreateView(self):
        """Make sure create view can create tags"""
        form_data = generate_form_data(model_form=TagForm)

        self.client.force_login(self.test_teacher)
        self.client.post(reverse('tags:create'), data=form_data)

        self.assertTrue(Tag.objects.filter(name=form_data['name']).exists())

    def test_UpdateView(self):
        """Make sure update view can change name + update slug"""
        form_data = generate_form_data(model_form=TagForm)

        self.client.force_login(self.test_teacher)
        self.client.post(reverse('tags:update', args=[self.tag.pk]), data=form_data)

        tag = Tag.objects.get(pk=self.tag.pk)  # refresh object
        self.assertEqual(form_data['name'], tag.name)
        self.assertEqual(form_data['name'].lower(), tag.slug)

    def test_DeleteView(self):
        """Make sure delete view can delete tag"""
        self.client.force_login(self.test_teacher)
        self.client.post(reverse('tags:delete', args=[self.tag.pk]))

        self.assertFalse(Tag.objects.filter(pk=self.tag.pk).exists())
