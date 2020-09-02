from django.contrib.auth import get_user_model
from django.shortcuts import reverse
from django import forms

from tenant_schemas.test.cases import TenantTestCase
from tenant_schemas.test.client import TenantClient

from hackerspace_online.forms import CustomSignupForm, PublicContactForm

User = get_user_model()


class CustomSignUpFormTest(TenantTestCase):

    def setUp(self):
        pass

    def test_init(self):
        CustomSignupForm()

    def test_valid_data(self):
        form = CustomSignupForm(
            {
                'username': "username",
                'first_name': "firsttest",
                'last_name': "Lasttest",
                'access_code': "314159",
                'password1': "password",
                'password2': "password"
            }
        )
        self.assertTrue(form.is_valid())

    def test_bad_access_codecoverage(self):
        """ Test that a sign up form with the wrong access code doesn't validate """
        form = CustomSignupForm(
            {
                'username': "username",
                'first_name': "firsttest",
                'last_name': "Lasttest",
                'access_code': "wrongcode",
                'password1': "password",
                'password2': "password"
            }
        )
        self.assertFalse(form.is_valid())

        with self.assertRaisesMessage(forms.ValidationError, "Access code unrecognized."):
            form.clean()

    def test_sign_up_via_post(self):
        self.client = TenantClient(self.tenant)
        form_data = {
            'username': "username",
            'first_name': "firsttest",
            'last_name': "Lasttest",
            'access_code': "314159",
            'password1': "password",
            'password2': "password"
        }
        response = self.client.post(reverse('account_signup'), form_data, follow=True,)
        self.assertRedirects(response, reverse('quests:quests'))
        user = User.objects.get(username="username")
        self.assertEqual(user.first_name, "firsttest")


class PublicContactFormTest(TenantTestCase):

    def setUp(self):
        pass

    def test_init(self):
        PublicContactForm()

    def test_valid_data(self):
        form = PublicContactForm(
            data={
                'name': 'First Last',
                'email': 'test@example.com',
                'message': 'Test Message',
                'g-recaptcha-response': 'PASSED',
            }
        )
        self.assertTrue(form.is_valid())
