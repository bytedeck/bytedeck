from io import StringIO
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.db.utils import OperationalError
from django.test import TestCase
from django_tenants.utils import tenant_context, get_public_schema_name, schema_context

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from model_bakery import baker

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


class InitDbTest(TestCase, CommandMixin):
    """ Note that this is NOT a TenantTestCase
    """
    name = "initdb"

    def test_initdb__sets_up_public_tenant(self):
        """ Test that initdb command sets up the public tenant, including:
        - a Tenant object called 'public'
        - a superuser
        - a Site object
        - a Flatpage object with url /pages/home/
        """
        self.call_command()

        public_tenant = Tenant.objects.get(schema_name="public")  # no assert, but will throw exception if doesn't exist

        with tenant_context(public_tenant):
            FlatPage.objects.get(url='/home/')  # no assert, but will throw exception if doesn't exist
            user = User.objects.get(username='admin')
            self.assertTrue(user.is_superuser)
            self.assertTrue(Site.objects.exists())

            Tenant.objects.get(schema_name=apps.get_app_config('library').TENANT_NAME)  # no assert, but will throw exception if doesn't exist

    def test_initdb__bails_when_database_is_unreachable(self):
        """If the initial DB connectivity check raises OperationalError, initdb reports it and
        bails without creating a superuser."""
        # Replace the module-level ``connections`` in initdb so its ``connections['default'].cursor()``
        # check raises; the surrounding @transaction.atomic still uses the real connection.
        mock_connections = MagicMock()
        mock_connections.__getitem__.return_value.cursor.side_effect = OperationalError

        with patch('hackerspace_online.management.commands.initdb.connections', mock_connections):
            out = self.call_command()

        self.assertIn("can't connect to the database", out)
        self.assertFalse(User.objects.filter(username=settings.DEFAULT_SUPERUSER_USERNAME).exists())

    def test_initdb__bails_when_superuser_already_exists(self):
        """Run twice: the second run finds the superuser from the first and bails without error,
        keeping initdb idempotent-safe."""
        self.call_command()
        out = self.call_command()

        self.assertIn(
            f'A superuser with username `{settings.DEFAULT_SUPERUSER_USERNAME}` already exists', out
        )
        # still exactly one superuser (the second run did not create another)
        self.assertEqual(User.objects.filter(username=settings.DEFAULT_SUPERUSER_USERNAME).count(), 1)

    def test_initdb__setup_shared_library_backfills_missing_domain(self):
        """setup_shared_library backfills the library tenant's domain when the tenant already
        exists but its domain is missing (e.g. a re-run after the domain was removed), rather
        than leaving the shared library unreachable."""
        from hackerspace_online.management.commands.initdb import Command

        self.call_command()
        library_schema = apps.get_app_config('library').TENANT_NAME
        library = Tenant.objects.get(schema_name=library_schema)
        library.domains.all().delete()
        self.assertFalse(library.domains.filter(domain='library.' + settings.ROOT_DOMAIN).exists())

        # The domain backfill runs before the (non-idempotent) library quest re-labelling, which
        # would re-prefix names and overflow Quest.name on a second run; patch it out so the test
        # targets only the domain-backfill branch.
        with patch('quest_manager.models.Quest'):
            Command().setup_shared_library()

        self.assertTrue(library.domains.filter(domain='library.' + settings.ROOT_DOMAIN).exists())

    def test_initdb__notes_when_public_tenant_already_existed(self):
        """When the public tenant already exists, initdb reports that (a not-created notice)
        instead of failing.

        The superuser guard is mocked to appear unset so the run proceeds to the public-tenant
        step (deleting the real superuser isn't possible here: its cascade touches per-tenant
        tables that don't exist in the public schema). The public domain is dropped first so the
        unconditional domain re-create doesn't hit the domain uniqueness constraint.
        """
        self.call_command()
        Tenant.objects.get(schema_name='public').domains.all().delete()

        # Mock the superuser guard to appear unset (so the run reaches the public-tenant step) and
        # skip setup_shared_library, whose non-idempotent quest re-labelling would overflow
        # Quest.name on a re-run and is unrelated to the public-tenant notice under test.
        with patch('hackerspace_online.management.commands.initdb.User') as MockUser, \
                patch('hackerspace_online.management.commands.initdb.Command.setup_shared_library'):
            MockUser.objects.filter.return_value.exists.return_value = False
            out = self.call_command()

        self.assertIn('A schema with the name `public` already existed', out)
        # the re-run reuses the existing homepage instead of adding a duplicate
        self.assertEqual(
            FlatPage.objects.filter(url='/home/', sites__domain=settings.ROOT_DOMAIN).count(), 1
        )


class GenerateContentTest(ByteDeckTenantTestCase, CommandMixin):
    """ generate_content adds items to an existing tenant.
    Dont need extensive testing as tests exist in "test_shell_utils.py"
    """
    name = "generate_content"

    def test_generate_content__adds_rows_to_db(self):
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
        """Initialize the public tenant and seed a tenant with a validation error."""
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

    def test_full_clean__captures_validation_errors(self):
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
            self.assertIn('test_schema1', log)

            # will cause an error because author is None because of
            # `null=True` without `blank=True`
            #  ie. `{'author': ['this field cannot be blank.']}`
            self.assertIn("'author': ['This field cannot be blank.']", log)
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
