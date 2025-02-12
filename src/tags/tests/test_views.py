import json

from django import forms
from django.core import signing
from django.contrib.auth import get_user_model
from django.urls import reverse

from django.utils.text import slugify

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from model_bakery import baker
from tags.forms import TagForm
from tags.widgets import TaggitSelect2Widget
from taggit.forms import TagField
from taggit.models import Tag
from siteconfig.models import SiteConfig

from hackerspace_online.tests.utils import ViewTestUtilsMixin, generate_form_data

User = get_user_model()


class TaggitSelect2WidgetForm(forms.Form):
    tag = TagField(
        widget=TaggitSelect2Widget(),
    )


class AutoResponseViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        Tag.objects.create(name="test-tag")

    def test_autocomplete_view(self):
        """ Make sure our custom django-select2 view for tag widget is accessible"""
        url = reverse('tags:auto-json')
        form = TaggitSelect2WidgetForm()
        assert form.as_p()
        field_id = signing.dumps(form.fields['tag'].widget.uuid)
        response = self.client.get(url, {'field_id': field_id, 'term': 'test-tag'})
        self.assertEqual(response.status_code, 200)

    def test_autocomplete_view__unauthenticated(self):
        """ The view should return an empty json response if the user is not authenticated """
        self.client.logout()

        url = reverse('tags:auto-json')
        form = TaggitSelect2WidgetForm()
        assert form.as_p()
        field_id = signing.dumps(form.fields['tag'].widget.uuid)
        response = self.client.get(url, {'field_id': field_id, 'term': 'test-tag'})
        self.assertEqual(response.json()['results'], [])

    def test_autocomplete_view__authenticated(self):
        """ The view should return tags in json results if the user is authenticated """
        self.client.force_login(baker.make('User'))

        url = reverse('tags:auto-json')
        form = TaggitSelect2WidgetForm()
        assert form.as_p()
        field_id = signing.dumps(form.fields['tag'].widget.uuid)
        response = self.client.get(url, {'field_id': field_id, 'term': 'test-tag'})
        data = json.loads(response.content.decode('utf-8'))
        assert data['results']
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['text'], 'test-tag')


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
        self.assert302('tags:detail_student', args=[self.tag.pk, self.test_student.pk])
        self.assertRedirectsLogin('tags:detail_staff', args=[self.tag.pk])
        self.assertRedirectsLogin('tags:create')
        self.assertRedirectsLogin('tags:update', args=[self.tag.pk])
        self.assertRedirectsLogin('tags:delete', args=[self.tag.pk])

    def test_page_status_code__student(self):
        """Make sure the list/detail views are accessible students but create/update/delete are not"""
        self.client.force_login(self.test_student)

        self.assert200('tags:list')
        self.assert200('tags:detail_student', args=[self.tag.pk, self.test_student.pk])
        self.assert403('tags:detail_staff', args=[self.tag.pk])
        self.assert403('tags:create')
        self.assert403('tags:update', args=[self.tag.pk])
        self.assert403('tags:delete', args=[self.tag.pk])

    def test_page_status_code__teacher(self):
        """Make sure the everything is accessible to teachers"""
        self.client.force_login(self.test_teacher)

        self.assert200('tags:list')
        self.assert200('tags:detail_student', args=[self.tag.pk, self.test_student.pk])
        self.assert200('tags:detail_staff', args=[self.tag.pk])
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

    def test_DetailView___staff_view(self):
        """
            Make sure detail view displays related quest/badges correctly.
            Staff should have access to all quest and badges tagged to self.tag
        """
        # generate quests + badges and link to tag
        quest_set = baker.make('quest_manager.quest', _quantity=5)
        badge_set = baker.make('badges.badge', _quantity=5)
        [quest.tags.add(self.tag.name) for quest in quest_set]
        [badge.tags.add(self.tag.name) for badge in badge_set]

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('tags:detail_staff', args=[self.tag.pk]))

        # check if ALL quests and badges show up in view
        [self.assertContains(response, quest.name) for quest in quest_set]  # quest check
        [self.assertContains(response, badge.name) for badge in badge_set]  # badge check

    def test_DetailView__student_view(self):
        """
            Make sure detail view displays related quest/badges correctly.
            Students should only have access to quest and badges they have completed/earned
        """
        # generate quests + badges and link to tag
        quest_set = baker.make('quest_manager.quest', xp=1, _quantity=5)
        badge_set = baker.make('badges.badge', xp=1, _quantity=5)
        [quest.tags.add(self.tag.name) for quest in quest_set]
        [badge.tags.add(self.tag.name) for badge in badge_set]

        # only assign first set element from quest and badge to user
        # make 2 submission/assertion to check if total xp is calculated correctly
        for _i in range(2):
            baker.make(
                'quest_manager.questsubmission',
                quest=quest_set[0],
                user=self.test_student,
                is_completed=True,
                is_approved=True,
                semester=SiteConfig().get().active_semester,
            )
            baker.make('badges.badgeassertion', badge=badge_set[0], user=self.test_student)

        self.client.force_login(self.test_student)
        response = self.client.get(reverse('tags:detail_student', args=[self.tag.pk, self.test_student.pk]))

        # check if only the quest and badges self.test_student has completed shows up in view
        self.assertContains(response, quest_set[0].name)
        self.assertContains(response, quest_set[0].xp * 2)
        [self.assertNotContains(response, quest.name) for quest in quest_set[1:]]

        self.assertContains(response, badge_set[0].name)
        self.assertContains(response, badge_set[0].xp * 2)
        [self.assertNotContains(response, badge.name) for badge in badge_set[1:]]

        # assert title shows up -> <tag_name> Tag Details for <user_username>
        self.assertContains(response, self.tag.name)
        self.assertContains(response, self.test_student.username)

    def test_DetailView__student_view_ordinal(self):
        ''' test if detail view list the ordinal quests correctly '''
        num_subs = 5
        unrelated_quest = baker.make('quest_manager.quest', xp=1)
        repeatable_quest = baker.make('quest_manager.quest', name='Repeatable Quest', max_repeats=-1, xp=1)
        unrelated_quest.tags.add(self.tag.name)
        repeatable_quest.tags.add(self.tag.name)

        # submission for unrelated test
        baker.make(
            'quest_manager.questsubmission',
            quest=unrelated_quest,
            user=self.test_student,
            is_completed=True,
            is_approved=True,
            semester=SiteConfig().get().active_semester,
        )
        # create repeatable quest submissions
        for i in range(1, num_subs + 1, 1):
            baker.make(
                'quest_manager.questsubmission',
                quest=repeatable_quest,
                user=self.test_student,
                is_completed=True,
                is_approved=True,
                semester=SiteConfig().get().active_semester,
                ordinal=i
            )

        self.client.force_login(self.test_student)
        response = self.client.get(reverse('tags:detail_student', args=[self.tag.pk, self.test_student.pk]))

        # check if DetailView follows this format:
        #   Quest Name (1 XP)
        #   Quest Name (2) (1 XP)
        #   ...
        #   Quest Name (5) (1 XP)
        self.assertContains(response, f'{repeatable_quest.name} ({repeatable_quest.xp} XP)', html=True)
        for i in range(2, num_subs, 1):
            self.assertContains(response, f'{repeatable_quest.name} ({i}) ({repeatable_quest.xp} XP)', html=True)

    def test_CreateView(self):
        """Make sure create view can create tags"""
        form_data = generate_form_data(model_form=TagForm)

        self.client.force_login(self.test_teacher)
        self.client.post(reverse('tags:create'), data=form_data)

        self.assertTrue(Tag.objects.filter(name=slugify(form_data['name'])).exists())

    def test_CreateView__slug_validation(self):
        """
        Invalid slug names provided to Tag CreateView should be rejected
        validators that must be passed:
        validate_slug https://docs.djangoproject.com/en/4.2/ref/validators/#validate-slug
        validate_unique_slug (custom validator, located at tags.forms.validate_unique_slug)
        """

        # login a teacher to create tags
        self.client.force_login(self.test_teacher)

        # post to create form with an invalid name to trigger validator 'validate_slug'
        response = self.client.post(reverse('tags:create'), data={'name': 'invalid name'})

        # assert object is not created and error message displayed
        self.assertContains(response, 'Enter a valid “slug” consisting of letters, numbers, underscores or hyphens.')
        self.assertFalse(Tag.objects.filter(name='invalid name').exists())

        # post to create form with non-unique (after slugification) name to trigger validator 'validate_unique_slug'
        response = self.client.post(reverse('tags:create'), data={'name': 'TEST-TAG'})

        # assert object is not created and error message displayed
        self.assertContains(response, 'Tag name too similar to existing tag: test-tag')
        self.assertFalse(Tag.objects.filter(name='TEST-TAG').exists())

    def test_UpdateView(self):
        """Make sure update view can change name + update slug"""
        form_data = generate_form_data(model_form=TagForm)

        self.client.force_login(self.test_teacher)
        self.client.post(reverse('tags:update', args=[self.tag.pk]), data=form_data)

        tag = Tag.objects.get(pk=self.tag.pk)  # refresh object
        # Form data is set to lowercase as a part of form submission, final name/slug will be lowercase of what was entered
        self.assertEqual(form_data['name'].lower(), tag.name)
        self.assertEqual(form_data['name'].lower(), tag.slug)

    def test_DeleteView(self):
        """Make sure delete view can delete tag"""
        self.client.force_login(self.test_teacher)
        self.client.post(reverse('tags:delete', args=[self.tag.pk]))

        self.assertFalse(Tag.objects.filter(pk=self.tag.pk).exists())
