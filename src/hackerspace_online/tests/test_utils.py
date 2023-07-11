from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse

from django_tenants.test.cases import TenantTestCase
from django_tenants.test.client import TenantClient

from model_bakery import baker
from hackerspace_online.tests.utils import generate_form_data

from courses.forms import BlockForm, CourseStudentForm


class Utils_generate_form_data_Test(TenantTestCase):
    """
        Specialized test cases for hackerspace_online.tests.utils.generate_form_data_test()
        Test to see if data generated is form_valid and can be used in post requests with different forms and models
    """

    def setUp(self):
        self.client = TenantClient(self.tenant)
        self.teacher = get_user_model().objects.create(username="teacher", password="password", is_staff=True,)

    def test_valid_SiteConfigModel(self):
        """
            Basic test to see if generate_form_data works with SiteConfig model
        """
        SiteConfig = apps.get_model("siteconfig", "siteconfig")

        self.client.force_login(self.teacher)
        form_data = generate_form_data(model=SiteConfig, site_name="NEW SITE NAME")

        # post request test
        response = self.client.post(reverse('config:site_config_update_own'), data=form_data)
        self.assertEqual(response.status_code, 302)

        # assert changes
        self.assertEqual(SiteConfig.get().site_name, "NEW SITE NAME")

    def test_valid_RankModel(self):
        """
            Basic test to see if generate_form_data works with Rank model
        """
        Rank = apps.get_model("courses", "rank")

        self.client.force_login(self.teacher)
        form_data = generate_form_data(model=Rank, name="NEW RANK NAME")

        # post request test
        response = self.client.post(reverse('courses:rank_create'), data=form_data)
        self.assertEqual(response.status_code, 302)

        # assert changes
        self.assertTrue(Rank.objects.filter(name="NEW RANK NAME").exists())

    def test_valid_BlockForm(self):
        """
            Basic test to see if generate_form_data works with BlockForm
        """
        Block = apps.get_model("courses", "block")

        self.client.force_login(self.teacher)
        form_data = generate_form_data(model_form=BlockForm, name="NEW BLOCK NAME")

        # form valid test
        form = BlockForm(form_data)
        self.assertTrue(form.is_valid())

        # post request test
        response = self.client.post(reverse('courses:block_create'), data=form_data)
        self.assertEqual(response.status_code, 302)

        # assert changes
        self.assertTrue(Block.objects.filter(name="NEW BLOCK NAME").exists())

    def test_valid_CourseStudentForm(self):
        """
            Basic test to see if generate_form_data works with CourseStudentForm

            Also Tests for how generate_form_data will react to nullable "optional values"
            that are necessary for form to be valid

            Since validators aren't compatible with baker expected should be empty strings in form + form invalid
        """

        Block = apps.get_model("courses", "block")
        Course = apps.get_model("courses", "course")
        Semester = apps.get_model("siteconfig", "siteconfig").get().active_semester
        # Grade = apps.get_model("courses", "grade")

        CourseStudent = apps.get_model("courses", "coursestudent")

        form_data_valid = generate_form_data(
            model_form=CourseStudentForm,
            block=baker.make(Block),
            course=baker.make(Course),
            semester=Semester,
            # grade_fk=baker.make(Grade)
        )
        form_data_invalid = generate_form_data(CourseStudent)

        self.client.force_login(self.teacher)

        # form valid test
        form = CourseStudentForm(form_data_valid)
        self.assertTrue(form.is_valid())

        # form invalid test
        form = CourseStudentForm(form_data_invalid)
        self.assertFalse(form.is_valid())

        # post request test
        response = self.client.post(reverse('courses:create'), data=form_data_valid)
        self.assertEqual(response.status_code, 302)

        # assert changes
        self.assertTrue(CourseStudent.objects.count(), 1)
