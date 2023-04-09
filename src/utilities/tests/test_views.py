import json
import random
import string

from django import forms
from django.core import signing
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils.encoding import smart_text
from django.contrib.flatpages.models import FlatPage
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.urls import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from queryset_sequence import QuerySetSequence

from utilities.models import MenuItem
from utilities.fields import GFKChoiceField
from utilities.widgets import GFKSelect2Widget
from hackerspace_online.tests.utils import ViewTestUtilsMixin

User = get_user_model()


def random_string(n):
    return "".join(
        random.choice(string.ascii_uppercase + string.digits) for _ in range(n)
    )


class GFKSelect2WidgetForm(forms.Form):
    f = GFKChoiceField(
        queryset=QuerySetSequence(
            Group.objects.all(),
        ),
        widget=GFKSelect2Widget(
            search_fields={
                'auth': {'group': ['name__icontains']}}
        )
    )


class CustomGFKSelect2Widget(GFKSelect2Widget):
    queryset = QuerySetSequence(Group.objects.all())
    search_fields = {
        'auth': {'group': ['name__icontains']},
    }

    def label_from_instance(self, obj):
        return str(obj.name).upper()


class TestAutoResponseView(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        self.groups = Group.objects.bulk_create(
            [Group(pk=pk, name=random_string(50)) for pk in range(100)]
        )

    def _ct_pk(self, obj):
        return "{}-{}".format(ContentType.objects.get_for_model(obj).pk, obj.pk)

    def test_get(self):
        group = self.groups[0]
        form = GFKSelect2WidgetForm()
        assert form.as_p()
        field_id = signing.dumps(id(form.fields['f'].widget))
        url = reverse('utilities:querysetsequence_auto-json')
        response = self.client.get(url, {'field_id': field_id, 'term': group.name})
        assert response.status_code == 200
        data = json.loads(response.content.decode('utf-8'))
        assert data['results']
        assert {'id': self._ct_pk(group), 'text': smart_text(group)} in data['results'][0]['children']

    def test_no_field_id(self):
        group = self.groups[0]
        url = reverse('utilities:querysetsequence_auto-json')
        response = self.client.get(url, {'term': group.name})
        assert response.status_code == 404

    def test_wrong_field_id(self):
        group = self.groups[0]
        url = reverse('utilities:querysetsequence_auto-json')
        response = self.client.get(url, {'field_id': 123, 'term': group.name})
        assert response.status_code == 404

    def test_field_id_not_found(self):
        group = self.groups[0]
        field_id = signing.dumps(123456789)
        url = reverse('utilities:querysetsequence_auto-json')
        response = self.client.get(url, {'field_id': field_id, 'term': group.name})
        assert response.status_code == 404

    def test_pagination(self):
        url = reverse('utilities:querysetsequence_auto-json')
        widget = GFKSelect2Widget(
            max_results=10,
            queryset=QuerySetSequence(Group.objects.all()),
            search_fields={
                'auth': {'group': ['name__icontains']},
            }
        )
        widget.render('name', None)
        field_id = signing.dumps(id(widget))

        response = self.client.get(url, {'field_id': field_id, 'term': ''})
        assert response.status_code == 200
        data = json.loads(response.content.decode('utf-8'))
        assert data['more'] is True

        response = self.client.get(url, {'field_id': field_id, 'term': '', 'page': 1000})
        assert response.status_code == 404

        response = self.client.get(url, {'field_id': field_id, 'term': '', 'page': 'last'})
        assert response.status_code == 200
        data = json.loads(response.content.decode('utf-8'))
        assert data['more'] is False

    def test_label_from_instance(self):
        url = reverse('utilities:querysetsequence_auto-json')

        form = GFKSelect2WidgetForm()
        form.fields['f'].widget = CustomGFKSelect2Widget()
        assert form.as_p()
        field_id = signing.dumps(id(form.fields['f'].widget))

        # artist = artists[0]
        group = self.groups[0]
        response = self.client.get(url, {'field_id': field_id, 'term': group.name})
        assert response.status_code == 200

        data = json.loads(response.content.decode('utf-8'))
        assert data['results']
        assert {'id': self._ct_pk(group), 'text': smart_text(group.name.upper())} in data['results'][0]['children']

    def test_url_check(self):
        from django_select2.cache import cache

        group = self.groups[0]
        form = GFKSelect2WidgetForm()
        assert form.as_p()
        field_id = signing.dumps(id(form.fields['f'].widget))
        cache_key = form.fields['f'].widget._get_cache_key()
        widget_dict = cache.get(cache_key)
        widget_dict['url'] = 'yet/another/url'
        cache.set(cache_key, widget_dict)
        url = reverse('utilities:querysetsequence_auto-json')
        response = self.client.get(url, {'field_id': field_id, 'term': group.name})
        assert response.status_code == 404


class MenuItemViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        # need a teacher and a student with known password so tests can log in as each
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student = User.objects.create_user('test_student', password=self.test_password)

    def test_all_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to login '''
        self.assertRedirectsLogin('utilities:menu_items')
        self.assertRedirectsLogin('utilities:menu_item_create')
        self.assertRedirectsLogin('utilities:menu_item_update', args=[1])
        self.assertRedirectsLogin('utilities:menu_item_delete', args=[1])

    def test_all_page_status_codes_for_students(self):
        ''' If not logged in as admin then all views should redirect to 403 '''
        self.client.force_login(self.test_student)

        # Staff access only
        self.assert403('utilities:menu_items')
        self.assert403('utilities:menu_item_create')
        self.assert403('utilities:menu_item_update', args=[1])
        self.assert403('utilities:menu_item_delete', args=[1])

    def test_MenuItemList_view(self):
        ''' Admin should be able to view menu item list '''
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('utilities:menu_items'))
        self.assertEqual(response.status_code, 200)

    def test_MenuItemCreate_view(self):
        ''' Admin should be able to create a menu item '''
        self.client.force_login(self.test_teacher)
        data = {
            'label': 'New Menu Item',
            'fa_icon': 'fa-gift',
            'url': reverse('courses:ranks'),
            'open_link_in_new_tab': False,
            'sort_order': 0,
        }
        response = self.client.post(reverse('utilities:menu_item_create'), data=data)
        self.assertRedirects(response, reverse('utilities:menu_items'))

        test_menuitem = MenuItem.objects.get(label=data['label'])
        self.assertEqual(test_menuitem.label, data['label'])

    def test_MenuItemCreate_view__displays_leading_slash_error(self):
        """ Menu Item create view should display correct error text when a bad url is submitted"""
        self.client.force_login(self.test_teacher)
        data = {
            'label': 'New Menu Item',
            'fa_icon': 'fa-gift',
            'url': reverse('courses:ranks')[1:],
            'open_link_in_new_tab': False,
            'sort_order': 0,
        }

        # tests Menu Item creation without leading slash ((reverse('courses:ranks'))[1:]) == 'courses/ranks/'
        response = self.client.post(reverse('utilities:menu_item_create'), data=data)
        leading_slash_error = "Enter a valid URL."
        self.assertContains(response, leading_slash_error)

    def test_MenuItemUpdate_view(self):
        """ Admin should be able to update a Menu Item """
        self.client.force_login(self.test_teacher)
        # set label and icon to something they wouldn't normally be
        data = {
            'label': 'My Updated Name',
            'fa_icon': 'fa-bath',
            'url': reverse('courses:ranks'),
            'open_link_in_new_tab': False,
            'sort_order': 0,
        }
        response = self.client.post(reverse('utilities:menu_item_update', args=[1]), data=data)
        self.assertRedirects(response, reverse('utilities:menu_items'))
        test_menuitem = MenuItem.objects.get(id=1)
        self.assertEqual(test_menuitem.label, data['label'])
        self.assertEqual(test_menuitem.fa_icon, data['fa_icon'])

    def test_MenuItemUpdate_view__displays_leading_slash_error(self):
        """ Menu Item update view should display correct error text when a bad url is submitted"""
        self.client.force_login(self.test_teacher)
        data = {
            'label': 'My Updated Name',
            'fa_icon': 'fa-bath',
            'url': reverse('courses:ranks')[1:],
            'open_link_in_new_tab': False,
            'sort_order': 0,
        }

        # tests Menu Item updating without leading slash
        response = self.client.post(reverse('utilities:menu_item_update', args=[1]), data=data)
        leading_slash_error = "Enter a valid URL."
        self.assertContains(response, leading_slash_error)


class FlatPageViewTests(ViewTestUtilsMixin, TenantTestCase):

    @staticmethod
    def create_flatpage(**kwargs) -> FlatPage:
        """
            This is basically baker.make(FlatPage) but it actually works
        """
        def random_string(length):
            return ''.join(random.choice(string.ascii_letters) for i in range(length))
        data = {}

        for field in FlatPage._meta.fields:
            if field.name in kwargs:
                data[field.name] = kwargs[field.name]

            elif field.name == 'title':
                max_length = FlatPage._meta.get_field(field.name).max_length
                data[field.name] = random_string(max_length)

            elif field.name == 'url':
                max_length = FlatPage._meta.get_field(field.name).max_length - 2
                data[field.name] = f"/{random_string(max_length)}/"

        flatpage = FlatPage.objects.create(**data)
        flatpage.sites.add(Site.objects.first())

        return flatpage

    def setUp(self):
        self.client = TenantClient(self.tenant)
        User = get_user_model()

        self.test_password = "password"

        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)

        self.flatpage_nonlogin = [FlatPageViewTests.create_flatpage(registration_required=False) for i in range(3)]
        self.flatpage_login = [FlatPageViewTests.create_flatpage(registration_required=True) for i in range(3)]

    def test_all_page_status_codes_for_anonymous(self):
        """
            Redirects to admin or returns 200 if user is not logged in
        """
        self.assert200('utilities:flatpage_list')

        # Staff only
        self.assertRedirectsLogin('utilities:flatpage_create')
        self.assertRedirectsLogin('utilities:flatpage_edit', args=[1])
        self.assertRedirectsLogin('utilities:flatpage_delete', args=[1])

    def test_all_page_status_codes_for_students(self):
        """
            Redirects to 403 or returns 200 if user is is_staff=False
        """
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        self.assert200('utilities:flatpage_list')

        # Staff only
        self.assert403('utilities:flatpage_create')
        self.assert403('utilities:flatpage_edit', args=[1])
        self.assert403('utilities:flatpage_delete', args=[1])

    def test_all_page_status_codes_for_staff(self):
        """
            Should return 200 for all cases
        """
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        pk = FlatPage.objects.first().pk

        self.assert200('utilities:flatpage_list')
        self.assert200('utilities:flatpage_create')
        self.assert200('utilities:flatpage_edit', args=[pk])
        self.assert200('utilities:flatpage_delete', args=[pk])

    def test_login_requirements_for_flatpage(self):
        """
            Flatpage with login required can only be accessed by users,
            while flatpages without can be accessed by all
        """

        # check all exists in flatpage_list first
        response = self.client.get(reverse('utilities:flatpage_list'))
        for flatpage in self.flatpage_nonlogin + self.flatpage_login:
            self.assertContains(response, flatpage.title)

        # Without logging in

        # no login required
        for flatpage in self.flatpage_nonlogin:
            self.assert200URL(flatpage.get_absolute_url())

        # login requried
        for flatpage in self.flatpage_login:
            self.assertRedirectsLoginURL(flatpage.get_absolute_url())

        # With logging in
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        # no login required
        for flatpage in self.flatpage_nonlogin:
            self.assert200URL(flatpage.get_absolute_url())

        # login requried
        for flatpage in self.flatpage_login:
            self.assert200URL(flatpage.get_absolute_url())

    def test_flatpagelist__list(self):
        """
            Confirm that all flatpages are properly displayed
        """
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        response = self.client.get(reverse('utilities:flatpage_list'))

        for flatpage in self.flatpage_login + self.flatpage_nonlogin:
            self.assertContains(response, flatpage.title)

    def test_flatpagecreate__create(self):
        """
            Can create flatpage and access it
        """
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)
        data = {
            'url': '/flatpagecreate-test/',
            'title': 'flatpagecreate-test-title',
            'sites': [Site.objects.first().id],
        }

        # Redirect after creation
        response = self.client.post(reverse('utilities:flatpage_create'), data=data)
        self.assertRedirects(response, reverse('utilities:flatpage_list'))

        # Assert flatpage exists
        flatpages = FlatPage.objects.filter(url=data['url'])
        self.assertTrue(flatpages.exists())

        # Shows up in flatpage_list
        response = self.client.get(reverse('utilities:flatpage_list'))
        self.assertContains(response, data['title'])

        # Accessed in pages/
        self.assert200URL(flatpages.first().get_absolute_url())

    def test_flatpageupdate__update(self):
        """
            Confirm that flatpages are being updated using update view
        """
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        pre_update_data = {
            'url': '/pre_update_data-test-url/',
            'title': 'pre_update_data-test-title',
            'content': 'pre_update_data content content content',
        }
        post_update_data = {
            'url': '/post_update_data-test-url/',
            'title': 'post_update_data-test-title',
            'content': 'post_update_data content1 content1 content1',
            'sites': [Site.objects.first().id],  # neccessary
        }

        flatpage = FlatPageViewTests.create_flatpage(**pre_update_data)

        # Check pre-update variables are correct
        response = self.client.get(reverse('utilities:flatpage_list'))
        self.assertContains(response, pre_update_data['title'])

        response = self.client.get(flatpage.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pre_update_data['title'])
        self.assertContains(response, pre_update_data['content'])

        # update through view
        response = self.client.post(reverse('utilities:flatpage_edit', args=[flatpage.pk]), data=post_update_data)
        flatpage = FlatPage.objects.get(url=post_update_data['url'])
        self.assertRedirects(response, flatpage.get_absolute_url())

        # Check post-update variables are correct
        response = self.client.get(reverse('utilities:flatpage_list'))
        self.assertContains(response, post_update_data['title'])

        response = self.client.get(flatpage.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, post_update_data['title'])
        self.assertContains(response, post_update_data['content'])

    def test_flatpagedelete__delete(self):
        """
            Confirm that flatpages are being properly deleted
        """
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        flatpage = FlatPageViewTests.create_flatpage()
        absolute_url = flatpage.get_absolute_url()
        title = flatpage.title
        pk = flatpage.pk

        # confirm exists
        response = self.client.get(reverse('utilities:flatpage_list'))
        self.assertContains(response, title)

        # delete through view
        response = self.client.post(reverse('utilities:flatpage_delete', kwargs={'pk': pk}))
        self.assertRedirects(response, reverse('utilities:flatpage_list'))

        # check if deleted

        # doesnt exists in flatpage_list
        response = self.client.get(reverse('utilities:flatpage_list'))
        self.assertNotContains(response, title)

        # page does not exist
        self.assert404URL(absolute_url)
