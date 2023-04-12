from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django_tenants.test.cases import TenantTestCase

from hackerspace_online.tests.utils import generate_form_data
from ..forms import ProfileForm
from ..models import Profile


User = get_user_model()


class ProfileFormTest(TenantTestCase):

    def setUp(self) -> None:
        self.user = User.objects.create_user('test_student', password="test_password")

    def test_init(self):
        # Without request
        ProfileForm(instance=self.user.profile)

        request = RequestFactory().get('/')

        ProfileForm(instance=self.user.profile, request=request)

    def test_profile_save_without_request(self):
        """
        Test to increase coverage for ProfileForm
        """
        form_data = generate_form_data(
            model_form=ProfileForm,
            grad_year=Profile.get_grad_year_choices()[0][0]
        )
        form = ProfileForm(instance=self.user.profile, data=form_data)
        form.is_valid()
        form.save()

    def tearDown(self) -> None:
        self.user.delete()
