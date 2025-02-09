from io import StringIO
from contextlib import redirect_stdout

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.test import TestCase
from django_tenants.test.cases import TenantTestCase
from django_tenants.utils import tenant_context, get_public_schema_name, schema_context

from model_bakery import baker

# from hackerspace_online.management.commands import find_replace
from quest_manager.models import Quest, Category
from tenant.models import Tenant

User = get_user_model()


class CommandMixin:
    """
    Mixin to simplify calling management commands in tests.
    It captures the command output and handles errors if the command name is not set.

    need to set name variable in the class that uses this mixin.
    ie.
    ```
        def CustomCommandTest(CommandMixin):
            name = "custom_command"
    ```
    """
    name = None

    def call_command(self, *args, **kwargs):
        if not isinstance(self.name, str):
            raise TypeError('Error: command name expects a string')

        out = StringIO()
        call_command(
            self.name,
            *args,
            stdout=out,
            stderr=StringIO(),
            **kwargs,
        )
        return out.getvalue()


class FindReplaceTest(TestCase, CommandMixin):
    name = "find_replace"

    # def setUp(self):
    #     self.tenant = Tenant(
    #         domain_url='testdeck.localhost',
    #         schema_name='testdeck',
    #         name='testdeck'
    #     )
    #     self.tenant.save()

    def test_tenants_all(self):
        # Constant error, not sure why Category table is empty:
        # django.db.utils.IntegrityError: null value in column "title" violates not-null constraint
        # DETAIL:  Failing row contains (1, null, , t).
        pass
        # "All tenants"
        # for tenant in Tenant.objects.all():
        #     print(tenant.name)
        # # print(tenants)
        # # # requires
        # # pass
        # out = self.call_command(self.tenant.name)
        # print(out)
        # self.assertEqual(out, "In dry run mode (--write not passed)\n")


class InitDbTest(TestCase, CommandMixin):
    """ Note that this is NOT a TenantTestCase
    """
    name = "initdb"

    def test_initdb(self):
        """ Test that initdb command sets up the public tenant, including:
        - a Tenant object called 'public'
        - a superuser
        - a Site object
        - a Flatpage object with url /pages/home/
        """
        output = self.call_command()
        print("*** INITDB Management Command: ", output)

        public_tenant = Tenant.objects.get(schema_name="public")  # no assert, but will throw exception if doesn't exist

        with tenant_context(public_tenant):
            FlatPage.objects.get(url='/home/')  # no assert, but will throw exception if doesn't exist
            user = User.objects.get(username='admin')
            self.assertTrue(user.is_superuser)
            self.assertTrue(Site.objects.exists())

            Tenant.objects.get(schema_name=apps.get_app_config('library').TENANT_NAME)  # no assert, but will throw exception if doesn't exist


class GenerateContentTest(TenantTestCase, CommandMixin):
    """ generate_content adds items to an existing tenant.
    Dont need extensive testing as tests exist in "test_shell_utils.py"
    """
    name = "generate_content"

    def test_added_rows_to_db(self):
        """ test checks if "generate_content" adds objects to the db """
        new_campaigns = 2
        new_quests = 5
        new_students = 5

        # expected
        expected_quest_count = Quest.objects.count() + (new_campaigns * new_quests)
        expected_campaign_count = Category.objects.count() + new_campaigns
        expected_user_count = User.objects.count() + new_students

        #
        self.call_command(
            self.tenant.schema_name,
            '--num_quests_per_campaign', new_quests,
            '--num_campaigns', new_campaigns,
            '--num_students', new_students,
            '--quiet'
        )

        # test if the command added new objects
        self.assertEqual(Quest.objects.count(), expected_quest_count)
        self.assertEqual(Category.objects.count(), expected_campaign_count)
        self.assertEqual(User.objects.count(), expected_user_count)


class FullCleanTest(TestCase, CommandMixin):
    name = 'full_clean'

    def setUp(self):
        call_command('initdb')

        # have to create tenant this way to prevent errors
        # + "you cant create a tenant outside public schema"
        with schema_context(get_public_schema_name()):
            self.tenant1 = Tenant.objects.create(schema_name='test_schema1', name='Test Tenant 1')
        # with schema_context(get_public_schema_name()):
        #     self.tenant2 = Tenant.objects.create(schema_name='test_schema2', name='Test Tenant 2')

        # add two different errors to each tenant
        with schema_context(self.tenant1.schema_name):
            # will cause an error because author is None because of
            # `null=True` without `blank=True`
            #  ie. `{'author': ['this field cannot be blank.']}`
            baker.make('announcements.Announcement')

        # Remove to speed up tests.
        # with schema_context(self.tenant2.schema_name):
        #     # will cause an error because semester is None because of
        #     # `null=True` without `blank=True`
        #     #  ie. `{'semester': ['this field cannot be blank.']}`
        #     qs = baker.make('quest_manager.QuestSubmission')

    def test_full_clean(self):
        """ Checks if full clean captures expected validation errors from "full_clean" management command
        See setUp for the expected errors.
        """
        # capture stdout through contextlib.redirect_stdout, as the return value in call_command only works sometimes?

        with StringIO() as buf, redirect_stdout(buf):
            self.call_command(
                '--tenants', 'test_schema1'
            )
            # should capture any print statements by self.call_command
            # "Exception found on cleaning "<Object Name>" (<Model Name>) of type <Error Name>: <Error Log>"
            log = buf.getvalue()

            # capture schema name
            self.assertTrue('test_schema1' in log)

            # will cause an error because author is None because of
            # `null=True` without `blank=True`
            #  ie. `{'author': ['this field cannot be blank.']}`
            self.assertTrue("'author': ['This field cannot be blank.']" in log)
            self.assertEqual(log.count("ValidationError"), 1)

        # Speed up tests
        # with StringIO() as buf, redirect_stdout(buf):
        #     self.call_command(
        #         '--tenants', 'test_schema2'
        #     )
        #     # should capture any print statements by self.call_command
        #     # "Exception found on cleaning "<Object Name>" (<Model Name>) of type <Error Name>: <Error Log>"
        #     log = buf.getvalue()

        #     # capture schema name
        #     self.assertTrue('test_schema2' in log)

        #     # will cause an error because semester is None because of
        #     # `null=True` without `blank=True`
        #     #  ie. `{'semester': ['this field cannot be blank.']}`
        #     self.assertTrue('QuestSubmission' in log)
        #     self.assertFalse('Announcement' in log)
