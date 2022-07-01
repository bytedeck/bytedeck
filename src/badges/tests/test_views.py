import uuid

from django.contrib.auth import get_user_model
from django.urls import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from model_bakery import baker

from badges.models import Badge, BadgeAssertion, BadgeType
from hackerspace_online.tests.utils import ViewTestUtilsMixin
from siteconfig.models import SiteConfig

User = get_user_model()


class BadgeViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = baker.make(User)

        # needed because BadgeAssertions use a default that might not exist yet
        self.sem = SiteConfig.get().active_semester

        self.test_badge = baker.make(Badge, xp=5)
        self.test_badge_type = baker.make(BadgeType)
        self.test_assertion = baker.make(BadgeAssertion)

    def test_all_badge_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to home or admin page  '''
        b_pk = self.test_badge.pk
        a_pk = self.test_assertion.pk
        s_pk = self.test_student1.pk

        self.assertRedirectsLogin('badges:list')
        self.assertRedirectsLogin('badges:badge_detail', args=[b_pk])
        self.assertRedirectsLogin('badges:badge_create')

        self.assertRedirectsAdmin('badges:badge_update', args=[b_pk])
        self.assertRedirectsAdmin('badges:badge_copy', args=[b_pk])
        self.assertRedirectsAdmin('badges:badge_delete', args=[b_pk])
        self.assertRedirectsAdmin('badges:grant', args=[b_pk, s_pk])
        self.assertRedirectsAdmin('badges:bulk_grant_badge', args=[b_pk])
        self.assertRedirectsAdmin('badges:bulk_grant')
        self.assertRedirectsAdmin('badges:revoke', args=[a_pk])

    def test_all_badge_page_status_codes_for_students(self):

        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        b_pk = self.test_badge.pk
        # a_pk = self.test_assertion.pk
        s_pk = self.test_student1.pk

        self.assert200('badges:list')
        self.assert200('badges:badge_detail', args=[b_pk])

        # students shouldn't have access to these and should be redirected

        self.assertRedirectsQuests('badges:badge_create', follow=True),
        self.assertRedirectsAdmin('badges:badge_update', args=[b_pk])
        self.assertRedirectsAdmin('badges:badge_copy', args=[b_pk])
        self.assertRedirectsAdmin('badges:badge_delete', args=[b_pk])
        self.assertRedirectsAdmin('badges:grant', args=[b_pk, s_pk])
        self.assertRedirectsAdmin('badges:bulk_grant_badge', args=[b_pk])
        self.assertRedirectsAdmin('badges:bulk_grant')
        self.assertRedirectsAdmin('badges:revoke', args=[s_pk])

        self.assertEqual(self.client.get(reverse('badges:badge_prereqs_update', args=[b_pk])).status_code, 302)

    def test_all_badge_page_status_codes_for_teachers(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        b_pk = self.test_badge.pk
        a_pk = self.test_assertion.pk
        s_pk = self.test_student1.pk

        self.assert200('badges:list')
        self.assert200('badges:badge_detail', args=[b_pk])
        self.assert200('badges:badge_create')
        self.assert200('badges:badge_update', args=[b_pk])
        self.assert200('badges:badge_copy', args=[b_pk])
        self.assert200('badges:badge_delete', args=[b_pk])
        self.assert200('badges:grant', args=[b_pk, s_pk])
        self.assert200('badges:bulk_grant_badge', args=[b_pk])
        self.assert200('badges:bulk_grant')
        self.assert200('badges:revoke', args=[a_pk])
        self.assert200('badges:badge_prereqs_update', args=[a_pk])

    def test_badge_create(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        form_data = {
            'name': "badge test",
            'xp': 5,
            'content': "test content",
            'badge_type': self.test_badge_type.id,
            'author': self.test_teacher.id,
            'import_id': uuid.uuid4()
        }

        response = self.client.post(
            reverse('badges:badge_create'),
            data=form_data
        )
        self.assertRedirects(response, reverse("badges:list"))

        # Get the newest object
        new_badge = Badge.objects.latest('datetime_created')
        self.assertEqual(new_badge.name, "badge test")

    def test_badge_copy(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        form_data = {
            'name': "badge copy test",
            'xp': 5,
            'content': "test content",
            'badge_type': self.test_badge_type.id,
            'author': self.test_teacher.id,
            'import_id': uuid.uuid4()
        }

        response = self.client.post(
            reverse('badges:badge_copy', args=[self.test_badge.id]),
            data=form_data
        )
        self.assertRedirects(response, reverse("badges:list"))

        # Get the newest object
        new_badge = Badge.objects.latest('datetime_created')
        self.assertEqual(new_badge.name, "badge copy test")

    def test_assertion_create_and_delete(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        # test: assertion_create()
        form_data = {
            'badge': self.test_badge.id,
            'user': self.test_student1.id
        }

        response = self.client.post(
            reverse('badges:grant', kwargs={'user_id': self.test_student1.id, 'badge_id': self.test_badge.id}),
            data=form_data
        )
        self.assertRedirects(response, reverse("badges:list"))

        new_assertion = BadgeAssertion.objects.latest('timestamp')
        self.assertEqual(new_assertion.user, self.test_student1)
        self.assertEqual(new_assertion.badge, self.test_badge)

        # test: assertion_delete()
        response = self.client.post(
            reverse('badges:revoke', args=[new_assertion.id]),
        )
        self.assertRedirects(response, reverse("profiles:profile_detail", args=[self.test_student1.profile.id]))

        # shouldn't exist anymore now that we deleted it!
        with self.assertRaises(BadgeAssertion.DoesNotExist):
            BadgeAssertion.objects.get(id=new_assertion.id)

    def test_assertion_create_no_xp(self):
        """Don't grant XP for this badge assertion"""
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        # No XP granted for this badge
        form_data = {
            'badge': self.test_badge.id,
            'user': self.test_student1.id, 
            'do_not_grant_xp': True,
        }

        response = self.client.post(
            reverse('badges:grant', kwargs={'user_id': self.test_student1.id, 'badge_id': self.test_badge.id}),
            data=form_data
        )
        self.assertRedirects(response, reverse("badges:list"))
        
        new_assertion = BadgeAssertion.objects.latest('timestamp')
        self.assertEqual(new_assertion.do_not_grant_xp, True)

    def test_bulk_assertion_create(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        # compare total granted before to after:
        badge_assertions_before = BadgeAssertion.objects.all().count()

        # this form uses students in the active semester, so need to give them a course in the active semester!
        baker.make('courses.CourseStudent', user=self.test_student1, semester=self.sem)
        baker.make('courses.CourseStudent', user=self.test_student2, semester=self.sem)

        form_data = {
            'badge': self.test_badge.id,
            'students': [self.test_student1.profile.id, self.test_student2.profile.id]
        }
        response = self.client.post(reverse('badges:bulk_grant'), data=form_data)

        self.assertRedirects(response, reverse("badges:list"))

        # we just bulk granted 2 badges, so there should be two more than before!
        badge_assertions_after = BadgeAssertion.objects.all().count()
        self.assertEqual(badge_assertions_after, badge_assertions_before + 2)


class BadgeTypeViewTests(ViewTestUtilsMixin, TenantTestCase):

    def setUp(self):
        self.client = TenantClient(self.tenant)

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
    
        self.badge_type = baker.make(BadgeType)
    
    def test_all_page_status_codes_for_anonymous(self):
        ''' If not logged in then all views should redirect to home page or admin login '''
        self.assertRedirectsAdmin('badges:badge_types')
        self.assertRedirectsAdmin('badges:badge_type_create')
        self.assertRedirectsAdmin('badges:badge_type_update', args=[1])
        self.assertRedirectsAdmin('badges:badge_type_delete', args=[1])
    
    def test_all_page_status_codes_for_students(self):
        ''' If not logged in then all views should redirect to home page or admin login '''
        self.client.force_login(self.test_student1)

        # Staff access only
        self.assertRedirectsAdmin('badges:badge_types')
        self.assertRedirectsAdmin('badges:badge_type_create')
        self.assertRedirectsAdmin('badges:badge_type_update', args=[1])
        self.assertRedirectsAdmin('badges:badge_type_delete', args=[1])
    
    def test_BadgeTypeList_view(self):
        """ Admin should be able to view badge type list """
        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse('badges:badge_types'))
        self.assertEqual(response.status_code, 200)
    
    def test_BadgeTypeCreate_view(self):
        """ Admin should be able to create a course """
        self.client.force_login(self.test_teacher)
        data = {
            'name': 'New badge type',
            'fa_icon': 'fa-gift',
        }
        response = self.client.post(reverse('badges:badge_type_create'), data=data)
        self.assertRedirects(response, reverse('badges:badge_types'))

        test_badgetype = BadgeType.objects.get(name=data['name'])
        self.assertEqual(test_badgetype.name, data['name'])

    def test_BadgeTypeUpdate_view(self):
        """ Admin should be able to update a badge type """
        self.client.force_login(self.test_teacher)
        # set name and icon to something they wouldn't normally be
        data = {
            'name': 'My Updated Name',
            'fa_icon': 'fa-bath',
        }
        response = self.client.post(reverse('badges:badge_type_update', args=[1]), data=data)
        self.assertRedirects(response, reverse('badges:badge_types'))
        test_badgetype = BadgeType.objects.get(id=1)
        self.assertEqual(test_badgetype.name, data['name'])
        self.assertEqual(test_badgetype.fa_icon, data['fa_icon'])
    
    def test_BadgeTypeDelete_view__no_badges(self):
        """ Admin should be able to delete a badge type with no assigned badges """
        self.client.force_login(self.test_teacher)

        # make a new badge type that doesn't have any associated badges to ensure deleting it won't cause problems
        temporary_badgetype = baker.make(BadgeType)
        before_delete_count = BadgeType.objects.count()
        response = self.client.post(reverse('badges:badge_type_delete', args=[BadgeType.objects.filter(name=temporary_badgetype.name)[0].id]))
        after_delete_count = BadgeType.objects.count()
        self.assertRedirects(response, reverse('badges:badge_types'))
        self.assertEqual(before_delete_count - 1, after_delete_count)

    def test_BadgeTypeDelete_view__with_badges(self):
        """ Admin should not be able to delete a badge type with badges assigned """
        self.client.force_login(self.test_teacher)

        # assign badge to badge type
        badge = baker.make(Badge, xp=5, badge_type=self.badge_type)
        self.assertEqual(badge.badge_type, self.badge_type)

        # check if prevented delete from view using POST
        response = self.client.post(reverse('badges:badge_type_delete', args=[BadgeType.objects.filter(name=self.badge_type.name)[0].id]))
        self.assertNotEqual(response.status_code, 302)
        self.assertEqual(response.status_code, 200)

        # confirm badge type exists
        self.assertTrue(BadgeType.objects.filter(name=self.badge_type.name).exists())

        # confirm deletion prevention text shows up
        dt_ptag = f"Unable to delete badge type '{self.badge_type.name}'"
        self.assertContains(response, dt_ptag)
