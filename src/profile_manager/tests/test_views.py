import re
from unittest.mock import patch
from allauth.account.models import EmailConfirmationHMAC
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient
from model_bakery import baker

from hackerspace_online.tests.utils import ViewTestUtilsMixin
from siteconfig.models import SiteConfig

from profile_manager.forms import ProfileForm, UserForm

from hackerspace_online.tests.utils import generate_form_data


class ProfileViewTests(ViewTestUtilsMixin, TenantTestCase):

    # includes some basic model data
    # fixtures = ['initial_data.json']

    def setUp(self):
        self.client = TenantClient(self.tenant)
        User = get_user_model()

        # need a teacher and a student with known password so tests can log in as each, or could use force_login()?
        self.test_password = "password"

        # need a teacher before students can be created or the profile creation will fail when trying to notify
        self.test_teacher = User.objects.create_user('test_teacher', password=self.test_password, is_staff=True)
        self.test_student1 = User.objects.create_user('test_student', password=self.test_password)
        self.test_student2 = baker.make(User)

        # create semester with pk of default semester
        # this seems backward, but no semesters should exist yet in the test, so their shouldn't be any conflicts.
        self.active_sem = SiteConfig.get().active_semester

    def tearDown(self):
        cache.clear()

    def test_courses_correct_displayed_text(self):
        """
            Admins in their course tab should only see: 'Not applicable to staff users.'
            Students that havent joined a course should only be able to see: 'You have not joined a course yet for this semester'
            else should see course
        """
        course = baker.make('courses.Course', title='Test Course')
        tpk = self.test_teacher.profile.pk
        spk = self.test_student1.profile.pk

        # login as teacher/admin and check if 'add course' doesnt exists
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        # no course
        request = self.client.get(reverse('profiles:profile_detail', args=[tpk]))
        self.assertContains(request, 'Not applicable to staff users.')

        # with course
        baker.make('courses.CourseStudent', user=self.test_teacher, course=course)
        request = self.client.get(reverse('profiles:profile_detail', args=[tpk]))
        self.assertContains(request, 'Not applicable to staff users.')

        # login as student and check if 'add course' and 'course' exists
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        # no course
        request = self.client.get(reverse('profiles:profile_detail', args=[spk]))
        self.assertContains(request, 'You have not joined a course yet for this semester')

        # with course
        baker.make('courses.CourseStudent', user=self.test_student1, course=course)
        request = self.client.get(reverse('profiles:profile_detail', args=[spk]))
        self.assertContains(request, course.title)

    def test_all_profile_page_status_codes_for_anonymous(self):
        """ If not logged in then all views should redirect to home page  """

        self.assertRedirectsLogin('profiles:profile_list')
        self.assertRedirectsLogin('profiles:profile_list_current')
        self.assertRedirectsLogin('profiles:profile_list_inactive')
        self.assertRedirectsLogin('profiles:profile_list_staff')

    def test_all_profile_page_status_codes_for_students(self):

        # log in a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        s_pk = self.test_student1.profile.pk
        s2_pk = self.test_student2.profile.pk

        self.assert200('profiles:profile_detail', args=[s_pk])
        self.assert200('profiles:profile_update', args=[s_pk])
        self.assert200('profiles:tag_chart', args=[s_pk])

        self.assert200('profiles:profile_list_current')

        # students shouldn't have access to these and should be redirected to login or permission denied
        self.assert403('profiles:profile_list')
        self.assert403('profiles:profile_list_inactive')
        self.assert403('profiles:profile_list_staff')

        # viewing the profile of another student
        self.assertRedirectsQuests('profiles:profile_detail', args=[s2_pk])

        self.assertEqual(self.client.get(reverse('profiles:comment_ban', args=[s_pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('profiles:comment_ban_toggle', args=[s_pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('profiles:xp_toggle', args=[s_pk])).status_code, 403)
        # self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)

        self.assert404('profiles:profile_update', args=[s2_pk])

    def test_all_profile_page_status_codes_for_teachers(self):
        # log in a teacher
        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        s_pk = self.test_student1.profile.pk
        # s2_pk = self.test_student2.pk

        self.assert200('profiles:profile_detail', args=[s_pk])
        self.assert200('profiles:profile_update', args=[s_pk])
        self.assert200('profiles:profile_list')
        self.assert200('profiles:profile_list_current')
        self.assert200('profiles:profile_list_staff')
        self.assert200('profiles:profile_list_inactive')
        self.assert200('profiles:tag_chart', args=[s_pk])
        self.assertEqual(self.client.get(reverse('profiles:comment_ban', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:comment_ban_toggle', args=[s_pk])).status_code, 302)
        self.assertEqual(self.client.get(reverse('profiles:xp_toggle', args=[s_pk])).status_code, 302)
        # self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)

    def test_profile_recalculate_xp_status_codes(self):
        """Need to test this view with students in an active course"""
        # why testing this here?
        self.assertEqual(self.active_sem.pk, SiteConfig.get().active_semester.pk)

        self.assertEqual(self.client.get(reverse('profiles:recalculate_xp_current')).status_code, 302)

    def test_student_marks_button(self):
        """
        Student should be able to see marks button when `display_marks_calculation` is True.
        Otherwise, they should not be able to see it.
        """

        # Login a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        # View profile page
        s_pk = self.test_student1.profile.pk

        # `display_marks_calculation` is disabled by default. Student should not be able to view it
        response = self.client.get(reverse('profiles:profile_detail', args=[s_pk]))
        self.assertNotContains(response, 'View your Mark Calculations')

        config = SiteConfig.get()
        config.display_marks_calculation = True
        config.save()

        # Student should be able to view marks calculation
        response = self.client.get(reverse('profiles:profile_detail', args=[s_pk]))
        self.assertContains(response, 'View your Mark Calculations')

    def test_student_view_marks_404_if_disabled(self):
        """
        Student marks should return 404 if disabled by admin.
        """

        # Login a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        self.assert404('courses:my_marks')

    def test_student_view_marks_200_if_enabled(self):
        """
        Student marks page should be accessible if site admin has enabled it.
        """
        # Login a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        config = SiteConfig.get()
        config.display_marks_calculation = True
        config.save()

        self.assert200('courses:my_marks')

    def test_assert_correct_forms__not_staff(self):
        """
            test if non staff users have access to ProfileForm and not UserForm in ProfileView
        """
        self.client.force_login(self.test_student1)

        response = self.client.get(reverse("profiles:profile_update", args=[self.test_student1.profile.pk]))
        self.assertTrue(any(isinstance(form, ProfileForm) for form in response.context["forms"]))
        self.assertFalse(any(isinstance(form, UserForm) for form in response.context["forms"]))

    def test_assert_correct_forms__staff(self):
        """
            test if staff users have access to ProfileForm and UserForm in ProfileView
        """
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("profiles:profile_update", args=[self.test_teacher.profile.pk]))

        self.assertTrue(any(isinstance(form, ProfileForm) for form in response.context["forms"]))
        self.assertTrue(any(isinstance(form, UserForm) for form in response.context["forms"]))

    def test_update_profile__not_staff(self):
        """
            Test to see if a user who is_staff=False can use the UserForm using ProfileView
            (They shouldn't)
        """
        User = get_user_model()
        Profile = ProfileForm._meta.model

        user_instance = baker.make(User, email="old@email.com")
        profile_instance = user_instance.profile

        # ProfileForm form data
        form_data = generate_form_data(model_form=ProfileForm, grad_year=Profile.get_grad_year_choices()[0][0])
        # UserForm form data
        form_data.update({
            "username": "NEWUSERNAME",
            "email": "new@email.com",
            "first_name": "NEW",
            "last_name": "NEW",

            "is_staff": True,
            "is_active": True,
            "is_TA": False,
        })

        self.client.force_login(user_instance)

        # test if view accepts form data without errors
        response = self.client.post(reverse("profiles:profile_update", args=[profile_instance.pk]), data=form_data)
        self.assertRedirects(response, reverse("profiles:profile_detail", args=[profile_instance.pk]))

        # check if model data was changed
        self.assertTrue(User.objects.filter(email=form_data["email"]).exists())

        # check if staff args were ignored
        user_instance = User.objects.get(email=form_data["email"])
        self.assertFalse(user_instance.is_staff)

    def test_update_profile__staff(self):
        """
            Test to see if a user who is_staff=True can use the UserForm using ProfileView
            (They can)
        """
        User = get_user_model()
        Profile = ProfileForm._meta.model

        user_instance = baker.make(User, email="old@email.com", is_staff=True)
        profile_instance = user_instance.profile

        # ProfileForm form data
        form_data = generate_form_data(model_form=ProfileForm, grad_year=Profile.get_grad_year_choices()[0][0])
        # UserForm form data
        form_data.update({
            "username": "NEWUSERNAME",
            "email": "new@email.com",
            "first_name": "NEW",
            "last_name": "NEW",

            "is_staff": False,
            "is_active": True,
            "is_TA": True,
        })

        self.client.force_login(user_instance)

        # test if view accepts form data without errors
        response = self.client.post(reverse("profiles:profile_update", args=[profile_instance.pk]), data=form_data)
        self.assertRedirects(response, reverse("profiles:profile_detail", args=[profile_instance.pk]))

        # check if model data was changed
        self.assertTrue(User.objects.filter(email=form_data["email"]).exists())

        # check if other args were updated
        user_instance = User.objects.get(email=form_data["email"])
        self.assertEqual(user_instance.username, form_data["username"])
        self.assertEqual(user_instance.first_name, form_data["first_name"])
        self.assertEqual(user_instance.last_name, form_data["last_name"])
        self.assertEqual(user_instance.is_staff, form_data["is_staff"])
        self.assertEqual(user_instance.profile.is_TA, form_data["is_TA"])

    def test_password_change_status_code__anonymous(self):
        self.assertRedirectsLogin("profiles:change_password", kwargs={"pk": self.test_teacher.pk})
        self.assertRedirectsLogin("profiles:change_password", kwargs={"pk": self.test_student1.pk})
        self.assertRedirectsLogin("profiles:change_password", kwargs={"pk": self.test_student2.pk})

    def test_password_change_status_code__student(self):
        self.client.force_login(self.test_student1)

        self.assert403("profiles:change_password", kwargs={"pk": self.test_teacher.pk})
        self.assert403("profiles:change_password", kwargs={"pk": self.test_student1.pk})
        self.assert403("profiles:change_password", kwargs={"pk": self.test_student2.pk})

    def test_password_change_status_code__staff(self):
        self.client.force_login(self.test_teacher)

        self.assert403("profiles:change_password", kwargs={"pk": self.test_teacher.pk})
        self.assert200("profiles:change_password", kwargs={"pk": self.test_student1.pk})
        self.assert200("profiles:change_password", kwargs={"pk": self.test_student2.pk})

    def test_update_password(self):
        """
            quick test to see if staff can change their user's password using passwordchange form
        """
        User = get_user_model()
        user_instance = User.objects.create_user(username="username", password=self.test_password)

        form_data = {
            'new_password1': 'xXxnewwordpassxXx123@',
            'new_password2': 'xXxnewwordpassxXx123@',
        }

        success = self.client.login(username=self.test_teacher.username, password=self.test_password)
        self.assertTrue(success)

        # test if view accepts form data without errors
        self.client.post(reverse("profiles:change_password", kwargs={"pk": user_instance.pk}), data=form_data)

        # login to confirm changed password
        success = self.client.login(username=user_instance.username, password=form_data['new_password1'])
        self.assertTrue(success)

    def test_profile_list(self):
        """
            quick test for ProfileList to see...
            - if profile_lists have the correct view_type
            - has correct queryset
        """
        # since ProfileList qs only filters for active=True, staff=False, students
        User = get_user_model()

        # these shouldnt show up in qs
        baker.make(User, username='1', is_active=False)
        baker.make(User, username='2', is_staff=True)

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("profiles:profile_list"))
        self.assertEqual(response.context['view_type'], response.context['VIEW_TYPES'].LIST)

        qs = response.context['object_list']  # should not have usernames: 1 and 2 in the qs
        self.assertTrue(qs.count(), 2)  # these are the test students
        filtered_qs = qs.filter(user__is_active=False) | qs.filter(user__is_staff=True)
        self.assertFalse(filtered_qs.exists())

    def test_profile_list_current(self):
        """
            quick test for ProfileListCurrent to see...
            - if profile_lists have the correct view_type

            no need to check for qs since its already tested in test_managers
        """

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("profiles:profile_list_current"))
        self.assertEqual(response.context['view_type'], response.context['VIEW_TYPES'].CURRENT)

    def test_profile_list_inactive(self):
        """
            quick test for ProfileListInactive to see...
            - if profile_lists have the correct view_type

            no need to check for qs since its already tested in test_managers
        """

        self.client.force_login(self.test_teacher)
        response = self.client.get(reverse("profiles:profile_list_inactive"))
        self.assertEqual(response.context['view_type'], response.context['VIEW_TYPES'].INACTIVE)

    def test_profile_list_staff(self):
        """
            quick test for ProfileListStaff to see...
            - if profile_lists have the correct view_type
            - has correct queryset
        """
        self.client.force_login(self.test_teacher)

        response = self.client.get(reverse("profiles:profile_list_staff"))
        self.assertEqual(response.context['view_type'], response.context['VIEW_TYPES'].STAFF)

        qs = response.context['object_list']
        self.assertEqual(qs.count(), 3)  # self.test_teacher, deck_owner, admin

    def test_profile_update_email(self):
        """
        Test that updating your email sends a confirmation link and logging in will
        have a reminder to verify email address if not yet verified.
        """

        self.client.force_login(self.test_student1)

        # current student does not have an email
        self.assertFalse(self.test_student1.email)

        # begin test of method: profile_manager.views.profile_resend_email_verification
        # Accessing the resend email verification should just display an error message that they don't have an email
        with patch("profile_manager.views.messages.error") as mock_messages_error:
            response = self.client.get(reverse("profiles:profile_resend_email_verification", args=[self.test_student1.profile.pk]))
            message = mock_messages_error.call_args[0][1]

        self.assertEqual(message, "User does not have an email")

        # end test of method: profile_manager.views.profile_resend_email_verification

        # Prepare new data for student
        email = f"{self.test_student1.username}@example.com"

        form_data = generate_form_data(model_form=ProfileForm, grad_year=timezone.now().date().year + 2)
        form_data.update({
            "email": email,
        })

        with patch("profile_manager.views.messages.add_message") as mock_add_message:
            self.client.post(reverse("profiles:profile_update", args=[self.test_student1.profile.pk]), data=form_data)
            message = mock_add_message.call_args[0][2]

        self.test_student1.refresh_from_db()
        self.assertEqual(self.test_student1.email, email)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(message, f"Confirmation e-mail sent to {email}.")

        # begin test of method: profile_manager.models.user_logged_in_verify_email_reminder_handler
        self.client.logout()
        # Verify that logging in will have a reminder to verify your email
        form_data = {
            "login": self.test_student1.username,
            "password": self.test_password,
        }

        with patch("profile_manager.models.messages.info") as mock_messages_info:
            self.client.post(reverse('account_login'), form_data, follow=True)
            mock_messages_info.assert_called()
            message = mock_messages_info.call_args[0][1]

        self.assertEqual(message, f"Please verify your email address: {self.test_student1.email}.")
        self.client.logout()
        # end test of method: profile_manager.models.user_logged_in_verify_email_reminder_handler

        self.client.force_login(self.test_student1)

        # Label should still be Not yet verified
        response = self.client.get(reverse("profiles:profile_update", args=[self.test_student1.profile.pk]))
        form = response.context['form']
        self.assertIn("Not yet verified", form.fields['email'].help_text)

        # Resend email verification
        response = self.client.get(reverse("profiles:profile_resend_email_verification", args=[self.test_student1.profile.pk]))

        # We should now have 2 received emails
        self.assertEqual(len(mail.outbox), 2)

        # Extract the HMAC from the email
        email_msg = mail.outbox[1].message().as_string()
        match = re.search(r'https?://\S+/[^/]+/(\S+)/', email_msg)
        assert match
        hmac_key = match.group(1)

        # Manually verify the email
        email_address = EmailConfirmationHMAC.from_key(hmac_key).confirm(response.wsgi_request)
        assert email_address

        self.assertTrue(email_address.verified)

        response = self.client.get(reverse("profiles:profile_update", args=[self.test_student1.profile.pk]))
        form = response.context['form']

        self.assertIn("Verified", form.fields['email'].help_text)

        # Accessing the resend verification should display that email is already verified
        with patch("profile_manager.views.messages.info") as mock_messages_info:
            response = self.client.get(reverse("profiles:profile_resend_email_verification", args=[self.test_student1.profile.pk]))
            message = mock_messages_info.call_args[0][1]

        self.assertEqual(message, "Your email address has already been verified.")

        # Here, we just check that the messages was never called
        self.client.logout()
        with patch("profile_manager.models.messages.info") as mock_messages_info:
            self.client.post(reverse('account_login'), form_data, follow=True)
            mock_messages_info.assert_not_called()

    def test_update_profile__email_already_exists(self):
        """
        Test changing an email to a user with an existing email address fails
        """

        self.test_student1.email = "existing@example.com"
        self.test_student1.save()

        self.test_student2.email = "current@example.com"
        self.test_student2.save()
        self.client.force_login(self.test_student2)

        form_data = generate_form_data(model_form=ProfileForm, grad_year=timezone.now().date().year + 2)
        form_data.update({
            "email": self.test_student1.email,  # Use test_student1 email
        })

        response = self.client.post(reverse("profiles:profile_update", args=[self.test_student2.profile.pk]), data=form_data)

        form = response.context['form']

        self.test_student2.refresh_from_db()

        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors['email'][0], 'A user is already registered with this email address')
        self.assertEqual(self.test_student2.email, "current@example.com")   # Should be the same email

    def test_update_profile__revert_email_to_original(self):
        """
        Test that changing an email address and then reverting it to the original succeeds
        """

        orig_email = "original@example.com"
        self.test_student1.email = orig_email
        self.test_student1.save()

        self.test_student1.emailaddress_set.create(email=self.test_student1.email, verified=True, primary=True)

        self.client.force_login(self.test_student1)

        new_email = "new@example.com"
        form_data = generate_form_data(model_form=ProfileForm, grad_year=timezone.now().date().year + 2)
        form_data.update({
            "email": new_email,
        })

        with patch("profile_manager.views.messages.add_message") as mock_add_message:
            self.client.post(reverse("profiles:profile_update", args=[self.test_student1.profile.pk]), data=form_data)
            message = mock_add_message.call_args[0][2]

        self.test_student1.refresh_from_db()

        # Should now use the new email
        self.assertEqual(self.test_student1.email, new_email)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(message, f"Confirmation e-mail sent to {new_email}.")

        # Revert back to the original email, ignore the confirmation email
        form_data = generate_form_data(model_form=ProfileForm, grad_year=timezone.now().date().year + 2)
        form_data.update({
            "email": orig_email,
        })

        self.client.post(reverse("profiles:profile_update", args=[self.test_student1.profile.pk]), data=form_data)
        message = mock_add_message.call_args[0][2]

        self.test_student1.refresh_from_db()
        self.assertEqual(self.test_student1.email, orig_email)

    def test_update_profile__custom_label_displayed(self):
        """student profile update view should change instances of "student" to match custom label set in siteconfig"""
        # Login a student
        success = self.client.login(username=self.test_student1.username, password=self.test_password)
        self.assertTrue(success)

        # Change custom_name_for_student to a non-default option
        config = SiteConfig.get()
        config.custom_name_for_student = "CustomStudent"
        config.save()

        # Get a student's profile settings request and assert it contains the custom label in both areas where it should be
        # ("How your names will be used" section and visible_to_other_students field)
        # both of these labels are lowercase as a part of the forms/templates they're a part of, so test for lowercase instances
        request = self.client.get(reverse('profiles:profile_update', args=[self.test_student1.profile.pk]))
        self.assertContains(request, "to other customstudents:")
        self.assertContains(request, "Your marks will be visible to other customstudents through the customstudent list.")
