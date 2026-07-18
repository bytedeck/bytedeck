from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.urls import reverse

from django_tenants.test.client import TenantClient

from model_bakery import baker
from hackerspace_online.tests.utils import ByteDeckTenantTestCase, generate_form_data

from courses.forms import BlockForm, CourseStudentForm


class Utils_generate_form_data_Test(ByteDeckTenantTestCase):
    """
        Specialized test cases for hackerspace_online.tests.utils.generate_form_data_test()
        Test to see if data generated is form_valid and can be used in post requests with different forms and models
    """

    @classmethod
    def setUpTestData(cls):
        cls.teacher = get_user_model().objects.create(username="teacher", is_staff=True,)

    def setUp(self):
        self.client = TenantClient(self.tenant)

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

    # currently non-functional, should be fine injecting student_registration kwarg manually as it's set in views and not via a field like
    # generate_form_data checks for, but kwargs is not defined when instancing a form even despite that...
    # was working at one point but some unforseen change has broken this test and a fix might be more effort than worth since this is a test
    # implemented for redundancy and there are many similarly-functional tests for other near-identical forms across site more suited to
    # this convienience method
    # form_valid_data exists as a dict but is being picked up as an arg instead of a kwarg and kwargs=form_valid_data upon creation does not fix
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

        # manually inject student_registration kwarg since set in view and not a part of fields, wont be picked up by generate_form_data
        form_data_valid['student_registration'] = False

        form_data_invalid = generate_form_data(CourseStudent)
        form_data_valid['student_registration'] = False
        self.client.force_login(self.teacher)

        # form valid test
        form = CourseStudentForm(form_data_valid, student_registration=False)
        self.assertTrue(form.is_valid())

        # form invalid test
        form = CourseStudentForm(form_data_invalid, student_registration=False)
        self.assertFalse(form.is_valid())

        # post request test
        response = self.client.post(reverse('courses:create'), data=form_data_valid)
        self.assertEqual(response.status_code, 302)

        # assert changes
        self.assertTrue(CourseStudent.objects.count(), 1)


class ByteDeckTenantTestCaseTest(ByteDeckTenantTestCase):
    """Regression tests for ByteDeckTenantTestCase's setUpTestData support.

    django-tenants' stock TenantTestCase.setUpClass skips Django TestCase's
    class-level setup, so setUpTestData never runs there. These tests prove that
    our base class (1) runs setUpTestData with the tenant schema active, and
    (2) preserves per-test isolation of the class-level data.

    Note: test methods run in alphabetical order; test_a_* mutates class data and
    test_b_* verifies the mutation did not leak into the next test.
    """

    @classmethod
    def setUpTestData(cls):
        """Class-level fixture that would silently never run on stock TenantTestCase."""
        cls.category = baker.make('quest_manager.Category', title='setuptestdata-probe')

    def test_setuptestdata_ran_in_tenant_schema(self):
        """setUpTestData ran, its data is queryable, and it was created in the test tenant's schema."""
        self.assertEqual(connection.schema_name, self.tenant.schema_name)
        self.assertTrue(
            apps.get_model('quest_manager', 'Category').objects.filter(title='setuptestdata-probe').exists()
        )

    def test_a_mutations_of_class_data_are_visible_within_a_test(self):
        """A test may freely mutate class-level data; changes are visible inside that test."""
        self.category.title = 'mutated'
        self.category.save()
        self.assertTrue(
            apps.get_model('quest_manager', 'Category').objects.filter(title='mutated').exists()
        )

    def test_b_mutations_of_class_data_do_not_leak_between_tests(self):
        """DB rows and in-memory attributes are restored between tests (runs after test_a_*)."""
        self.assertEqual(self.category.title, 'setuptestdata-probe')
        Category = apps.get_model('quest_manager', 'Category')
        self.assertFalse(Category.objects.filter(title='mutated').exists())
        self.assertTrue(Category.objects.filter(title='setuptestdata-probe').exists())
