from datetime import timedelta
from io import StringIO
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.flatpages.models import FlatPage
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import OperationalError
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone
from django_tenants.utils import tenant_context, get_public_schema_name, schema_context

from badges.models import Badge, BadgeAssertion
from comments.models import Comment
from courses.models import Block, CourseStudent, Semester
from hackerspace_online.management.commands.initdb import get_homepage_content
from hackerspace_online.management.commands.merge_users import SIMPLE_REASSIGNMENTS
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from notifications.models import Notification, UserNotificationOptionSet
from portfolios.models import Artwork, Portfolio
from prerequisites.models import PrereqAllConditionsMet
from siteconfig.models import SiteConfig

from model_bakery import baker

from quest_manager.models import Quest, Category, QuestSubmission
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
            homepage = FlatPage.objects.get(url='/home/')  # will throw exception if doesn't exist
            # ALL THREE seeded TRY IT buttons must point at the deck-request form:
            # the old "#contact" anchor target no longer exists anywhere on the page
            self.assertEqual(homepage.content.count('href="/decks/request/"'), 3)
            self.assertNotIn('href="#contact"', homepage.content)
            user = User.objects.get(username='admin')
            self.assertTrue(user.is_superuser)
            self.assertTrue(Site.objects.exists())

            Tenant.objects.get(schema_name=apps.get_app_config('library').TENANT_NAME)  # no assert, but will throw exception if doesn't exist

    def test_initdb__gives_the_shared_library_a_reachable_domain(self):
        """A single initdb run leaves the Library deck reachable at library.<ROOT_DOMAIN> (#2382).

        The tenant post_save signal derives a domain from the tenant's name, and the Library
        tenant is named 'Shared Library', so the derived domain contains a space and can never
        be reached. initdb has to set the intended domain itself, on the first run rather than
        only on a re-run against a database where the tenant already exists.
        """
        self.call_command()

        library_tenant = Tenant.objects.get(schema_name=apps.get_app_config('library').TENANT_NAME)
        primary_domain = library_tenant.get_primary_domain().domain

        self.assertEqual(primary_domain, f'library.{settings.ROOT_DOMAIN}')
        # no leftover unreachable domain beside it, or the deck answers on a host nobody can type
        self.assertEqual(
            list(library_tenant.domains.values_list('domain', flat=True)),
            [f'library.{settings.ROOT_DOMAIN}'],
        )

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

    def test_initdb__setup_shared_library_leaves_a_correct_domain_alone(self):
        """setup_shared_library leaves the library tenant's domain untouched when it is already
        the intended one, rather than deleting and re-creating it on every run.

        The domain row's pk is the tell: a delete-and-recreate would hand out a new one.
        """
        from hackerspace_online.management.commands.initdb import Command

        self.call_command()
        library_schema = apps.get_app_config('library').TENANT_NAME
        library = Tenant.objects.get(schema_name=library_schema)
        domain_before = library.get_primary_domain()

        # As above: patch out the non-idempotent library quest re-labelling, which would
        # re-prefix names and overflow Quest.name on a second run.
        with patch('quest_manager.models.Quest'):
            Command().setup_shared_library()

        domain_after = library.get_primary_domain()
        self.assertEqual(domain_after.pk, domain_before.pk)
        self.assertEqual(domain_after.domain, 'library.' + settings.ROOT_DOMAIN)
        self.assertEqual(library.domains.count(), 1)

    def test_initdb__setup_shared_library_drops_a_stale_domain_beside_the_correct_one(self):
        """setup_shared_library removes any other domain on the library tenant, so the deck
        answers on library.<ROOT_DOMAIN> and nothing else.

        A tenant can end up with a second domain because the post_save signal derives one from
        the tenant's name; leaving it in place would keep the Library reachable on a host nobody
        intended (#2382).
        """
        from hackerspace_online.management.commands.initdb import Command

        self.call_command()
        library_schema = apps.get_app_config('library').TENANT_NAME
        library = Tenant.objects.get(schema_name=library_schema)
        library.domains.create(domain='stale.' + settings.ROOT_DOMAIN, is_primary=True)

        # As above: patch out the non-idempotent library quest re-labelling, which would
        # re-prefix names and overflow Quest.name on a second run.
        with patch('quest_manager.models.Quest'):
            Command().setup_shared_library()

        self.assertEqual(
            list(library.domains.values_list('domain', flat=True)),
            [f'library.{settings.ROOT_DOMAIN}'],
        )
        # and the survivor is the primary, even though the stale one held that flag
        self.assertEqual(library.get_primary_domain().domain, f'library.{settings.ROOT_DOMAIN}')

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


class GetHomepageContentTest(SimpleTestCase):
    """The seeded public homepage HTML must build image URLs from STATIC_URL.

    Guards against regressing to a hardcoded CDN domain (the real production
    CloudFront distribution was previously baked into every seeded homepage).
    """

    def test_get_homepage_content__derives_image_urls_from_static_url(self):
        """Every image src uses settings.STATIC_URL, with no hardcoded CDN domain."""
        with override_settings(STATIC_URL='https://cdn.example.test/static/'):
            html = get_homepage_content()
        # All homepage images resolve against the STATIC_URL-derived base...
        self.assertIn('https://cdn.example.test/static/public/images/wordmark-v2.png', html)
        self.assertEqual(html.count('https://cdn.example.test/static/public/images/'), 10)
        # ...and no real production CDN identifier is baked into the seed content.
        self.assertNotIn('cloudfront.net', html)
        self.assertNotIn('d10ge8y4vx8iud', html)

    def test_get_homepage_content__local_static_url_yields_relative_paths(self):
        """With the local dev STATIC_URL, image URLs are relative /static/ paths."""
        with override_settings(STATIC_URL='/static/'):
            html = get_homepage_content()
        self.assertIn('/static/public/images/wordmark-v2.png', html)
        self.assertEqual(html.count('/static/public/images/'), 10)
        self.assertNotIn('cloudfront.net', html)


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

    def test_generate_content__nonexistent_schema_raises_command_error(self):
        """A schema name with no matching tenant raises CommandError instead of failing obscurely."""
        with self.assertRaises(CommandError):
            self.call_command('does_not_exist_schema')


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


class MergeUsersTest(ByteDeckTenantTestCase, CommandMixin):
    """The merge_users command folds one account's work into another and deletes the duplicate."""

    name = "merge_users"

    def setUp(self):
        """Two students, one kept and one merged away, and a quest and badge to earn."""
        self.past = User.objects.create_user('past.student', password='password')
        self.current = User.objects.create_user('current.student', password='password')
        self.teacher = User.objects.create_user('teacher', password='password', is_staff=True)
        self.quest = baker.make(Quest, name='Write a haiku')
        self.badge = baker.make(Badge, name='Poet', xp=10)
        self.semester = SiteConfig.get().active_semester

    def merge(self, *args, **kwargs):
        """Run the command on the two students without the confirmation prompt."""
        return self.call_command(
            kwargs.pop('source', self.past.username),
            kwargs.pop('target', self.current.username),
            '--noinput',
            *args,
            **kwargs,
        )

    def test_merge_users__moves_quest_submissions_to_the_kept_account(self):
        """Work handed in on the duplicate account belongs to the kept account afterwards."""
        submission = baker.make(QuestSubmission, user=self.past, quest=self.quest, semester=self.semester)

        self.merge()

        submission.refresh_from_db()
        self.assertEqual(submission.user, self.current)

    def test_merge_users__moves_badges_to_the_kept_account(self):
        """Badges earned on the duplicate account are held by the kept account afterwards."""
        assertion = baker.make(BadgeAssertion, user=self.past, badge=self.badge, semester=self.semester)

        self.merge()

        assertion.refresh_from_db()
        self.assertEqual(assertion.user, self.current)

    def test_merge_users__moves_badges_the_source_issued(self):
        """A badge the duplicate account granted to someone else is re-credited, not orphaned."""
        assertion = baker.make(BadgeAssertion, user=self.teacher, badge=self.badge, issued_by=self.past)

        self.merge()

        assertion.refresh_from_db()
        self.assertEqual(assertion.issued_by, self.current)

    def test_merge_users__moves_course_registrations(self):
        """The duplicate's course registrations become the kept account's."""
        registration = baker.make(CourseStudent, user=self.past, semester=self.semester)

        self.merge()

        registration.refresh_from_db()
        self.assertEqual(registration.user, self.current)

    def test_merge_users__moves_comments(self):
        """Comments written on the duplicate account keep their text under the kept account."""
        comment = baker.make(Comment, user=self.past, text='my work', target_object=self.quest)

        self.merge()

        comment.refresh_from_db()
        self.assertEqual(comment.user, self.current)

    def test_merge_users__moves_notifications(self):
        """Notifications addressed to the duplicate are readable on the kept account."""
        notification = baker.make(
            Notification, recipient=self.past, sender_object=self.teacher, target_object=self.quest,
        )

        self.merge()

        notification.refresh_from_db()
        self.assertEqual(notification.recipient, self.current)

    def test_merge_users__remaps_a_notification_naming_the_source_as_sender(self):
        """A notification whose sender is the duplicate names the kept account instead.

        The sender is a generic foreign key rather than a real one, so nothing in the database
        would have rewritten it: it would have gone on pointing at a deleted row.
        """
        notification = baker.make(
            Notification, recipient=self.teacher, sender_object=self.past, target_object=self.quest,
        )

        self.merge()

        notification.refresh_from_db()
        self.assertEqual(notification.sender_object, self.current)

    def test_merge_users__deletes_the_duplicate_account(self):
        """The merged-away account is gone, so nobody can sign in to it again."""
        past_id = self.past.pk

        self.merge()

        self.assertFalse(User.objects.filter(pk=past_id).exists())
        self.assertTrue(User.objects.filter(pk=self.current.pk).exists())

    def test_merge_users__recaches_the_kept_accounts_xp(self):
        """The kept account's cached XP counts the work that came over with the merge.

        The merge moves rows with updates, which do not fire the signals that normally keep
        xp_cached up to date, so the command works it out again itself.
        """
        self.quest.xp = 15
        self.quest.save()
        baker.make(CourseStudent, user=self.past, semester=self.semester, block=baker.make(Block))
        baker.make(
            QuestSubmission, user=self.past, quest=self.quest, semester=self.semester,
            is_completed=True, is_approved=True, do_not_grant_xp=False,
            first_time_completed=timezone.now(), time_approved=timezone.now(),
        )
        self.current.profile.refresh_from_db()
        self.assertEqual(self.current.profile.xp_cached, 0)

        self.merge()

        self.current.profile.refresh_from_db()
        self.assertEqual(self.current.profile.xp_cached, 15)

    def test_merge_users__renumbers_repeated_submissions(self):
        """Both accounts numbered their submissions from one, so the merged set is renumbered.

        The count of how many times a quest was done reads the highest ordinal, which would
        come out as one attempt instead of two while both rows were numbered 1.
        """
        baker.make(
            QuestSubmission, user=self.past, quest=self.quest, semester=self.semester, ordinal=1,
            is_completed=True, first_time_completed=timezone.now() - timedelta(days=2),
        )
        baker.make(
            QuestSubmission, user=self.current, quest=self.quest, semester=self.semester, ordinal=1,
            is_completed=True, first_time_completed=timezone.now(),
        )

        self.merge()

        ordinals = list(
            QuestSubmission.objects.filter(user=self.current, quest=self.quest)
            .order_by('ordinal').values_list('ordinal', flat=True)
        )
        self.assertEqual(ordinals, [1, 2])

    def test_merge_users__renumbers_repeated_badges(self):
        """Two badge assertions that were each the first of their account become the first and second."""
        baker.make(BadgeAssertion, user=self.past, badge=self.badge, ordinal=1, semester=self.semester)
        baker.make(BadgeAssertion, user=self.current, badge=self.badge, ordinal=1, semester=self.semester)

        self.merge()

        ordinals = list(
            BadgeAssertion.objects.filter(user=self.current, badge=self.badge)
            .order_by('ordinal').values_list('ordinal', flat=True)
        )
        self.assertEqual(ordinals, [1, 2])
        self.assertEqual(BadgeAssertion.objects.num_assertions(self.current, self.badge), 2)

    def test_merge_users__moves_portfolio_artwork(self):
        """Artwork from the duplicate's portfolio ends up in the kept account's portfolio.

        A portfolio's primary key is its user id, so it cannot be reassigned: the artwork
        moves and the emptied portfolio goes.
        """
        past_portfolio = baker.make(Portfolio, user=self.past)
        artwork = baker.make(Artwork, portfolio=past_portfolio, title='Sunset')

        self.merge()

        artwork.refresh_from_db()
        self.assertEqual(artwork.portfolio.user, self.current)
        self.assertEqual(Portfolio.objects.filter(user=self.current).count(), 1)

    def test_merge_users__moves_artwork_into_an_existing_portfolio(self):
        """A kept account that already has a portfolio gains the duplicate's artwork in it."""
        current_portfolio = baker.make(Portfolio, user=self.current)
        past_portfolio = baker.make(Portfolio, user=self.past)
        baker.make(Artwork, portfolio=current_portfolio, title='Mine')
        baker.make(Artwork, portfolio=past_portfolio, title='Theirs')

        self.merge()

        titles = set(Artwork.objects.filter(portfolio=current_portfolio).values_list('title', flat=True))
        self.assertEqual(titles, {'Mine', 'Theirs'})

    def test_merge_users__drops_a_course_registration_the_target_already_has(self):
        """Two registrations for the same semester and group are the same fact, so one is dropped.

        Moving it would break CourseStudent's uniqueness on (semester, block, user).
        """
        block = baker.make(Block)
        baker.make(CourseStudent, user=self.current, semester=self.semester, block=block)
        baker.make(CourseStudent, user=self.past, semester=self.semester, block=block)

        output = self.merge()

        self.assertEqual(CourseStudent.objects.filter(user=self.current, block=block).count(), 1)
        self.assertIn('duplicates one', output)

    def test_merge_users__says_what_a_dropped_registration_takes_with_it(self):
        """A dropped registration's XP adjustment and final marks are named before it goes.

        Matching on (semester, block) does not make two registrations the same row: the one
        being dropped can hold its own adjustment and the marks recorded when its semester was
        archived, and that is the operator's decision to make rather than a surprise.
        """
        block = baker.make(Block)
        baker.make(CourseStudent, user=self.current, semester=self.semester, block=block)
        baker.make(
            CourseStudent, user=self.past, semester=self.semester, block=block,
            xp_adjustment=50, final_xp=800, final_grade=91,
        )

        output = self.merge('--dry-run')

        self.assertIn('an XP adjustment of 50', output)
        self.assertIn('final marks (800 XP, 91%)', output)

    def test_merge_users__says_nothing_extra_for_a_plain_dropped_registration(self):
        """A dropped registration carrying no adjustment or marks is reported without a tail."""
        block = baker.make(Block)
        baker.make(CourseStudent, user=self.current, semester=self.semester, block=block)
        baker.make(CourseStudent, user=self.past, semester=self.semester, block=block)

        output = self.merge('--dry-run')

        self.assertIn('it will be dropped rather than moved.', output)
        self.assertNotIn('It carries', output)

    def test_merge_users__keeps_registrations_that_name_no_group(self):
        """Two registrations with no group set are not duplicates, so both are kept.

        The uniqueness CourseStudent enforces counts nulls as distinct, so neither row is in
        the other's way.
        """
        baker.make(CourseStudent, user=self.current, semester=self.semester, block=None)
        baker.make(CourseStudent, user=self.past, semester=self.semester, block=None)

        self.merge()

        self.assertEqual(CourseStudent.objects.filter(user=self.current).count(), 2)

    def test_merge_users__drops_an_in_progress_submission_the_target_already_has(self):
        """Two never-completed attempts at one quest cannot both move, so the duplicate's goes.

        QuestSubmission refuses a second never-yet-completed submission of a quest per semester.
        """
        baker.make(QuestSubmission, user=self.current, quest=self.quest, semester=self.semester)
        baker.make(QuestSubmission, user=self.past, quest=self.quest, semester=self.semester)

        output = self.merge()

        self.assertEqual(
            QuestSubmission.objects.filter(user=self.current, quest=self.quest).count(), 1
        )
        self.assertIn('In-progress submission', output)

    def test_merge_users__moves_a_social_account(self):
        """Signing in with the Google account that reached the duplicate now reaches the kept one."""
        social = baker.make(SocialAccount, user=self.past, provider='google', uid='12345')

        self.merge()

        social.refresh_from_db()
        self.assertEqual(social.user, self.current)

    def test_merge_users__moves_an_email_address_as_non_primary(self):
        """The duplicate's email is carried over, but the kept account's own stays primary."""
        baker.make(EmailAddress, user=self.current, email='kept@example.com', primary=True, verified=True)
        baker.make(EmailAddress, user=self.past, email='old@example.com', primary=True, verified=True)

        self.merge()

        moved = EmailAddress.objects.get(email='old@example.com')
        self.assertEqual(moved.user, self.current)
        self.assertFalse(moved.primary)
        self.assertTrue(EmailAddress.objects.get(email='kept@example.com').primary)

    def test_merge_users__refuses_to_carry_over_an_invalid_email(self):
        """A stored address that does not validate stops the merge with nothing applied.

        The merge is one transaction, so the accounts are left as they were and the operator
        can deal with the bad address first.
        """
        baker.make(EmailAddress, user=self.past, email='not-an-email', primary=True)
        submission = baker.make(QuestSubmission, user=self.past, quest=self.quest, semester=self.semester)

        with self.assertRaises(ValidationError):
            self.merge()

        submission.refresh_from_db()
        self.assertEqual(submission.user, self.past)
        self.assertTrue(User.objects.filter(pk=self.past.pk).exists())

    def test_merge_users__drops_an_email_the_target_already_has(self):
        """The same address on both accounts is kept once, on the account being kept."""
        baker.make(EmailAddress, user=self.current, email='same@example.com', primary=True)
        baker.make(EmailAddress, user=self.past, email='same@example.com')

        output = self.merge()

        addresses = EmailAddress.objects.filter(email='same@example.com')
        self.assertEqual(addresses.count(), 1)
        self.assertEqual(addresses.first().user, self.current)
        self.assertIn('already on', output)

    def test_merge_users__clears_the_stale_quest_availability_cache(self):
        """The cache of which quests a student can see is rebuilt, since their work moved."""
        baker.make(PrereqAllConditionsMet, user=self.past, model_name='quest_manager.quest', ids='[1]')
        baker.make(PrereqAllConditionsMet, user=self.current, model_name='quest_manager.quest', ids='[2]')

        self.merge()

        caches = PrereqAllConditionsMet.objects.filter(user=self.current, model_name='quest_manager.quest')
        self.assertEqual(caches.count(), 1)
        self.assertNotEqual(caches.first().ids, '[2]')

    def test_merge_users__keeps_the_targets_own_notification_options(self):
        """Notification options are one row per user, so the kept account's own row survives alone."""
        baker.make(UserNotificationOptionSet, user=self.past, quest_approved_without_comment=False)
        baker.make(UserNotificationOptionSet, user=self.current, quest_approved_without_comment=True)

        self.merge()

        options = UserNotificationOptionSet.objects.filter(user=self.current)
        self.assertEqual(options.count(), 1)
        self.assertTrue(options.first().quest_approved_without_comment)

    def test_merge_users__accepts_ids_instead_of_usernames(self):
        """--by-id names the accounts by primary key, for usernames that are hard to type."""
        past_id = self.past.pk

        self.call_command(str(self.past.pk), str(self.current.pk), '--by-id', '--noinput')

        self.assertFalse(User.objects.filter(pk=past_id).exists())

    def test_merge_users__refuses_an_id_that_names_nobody(self):
        """--by-id with an id nobody has, or something that is not an id at all, says so."""
        with self.assertRaisesMessage(CommandError, 'No user with id'):
            self.call_command('9999999', str(self.current.pk), '--by-id', '--noinput')

        with self.assertRaisesMessage(CommandError, 'No user with id'):
            self.call_command('past.student', str(self.current.pk), '--by-id', '--noinput')

    def test_merge_users__drops_an_empty_portfolio_without_making_one(self):
        """A duplicate whose portfolio holds nothing leaves the kept account without one."""
        baker.make(Portfolio, user=self.past)

        self.merge()

        self.assertFalse(Portfolio.objects.filter(user=self.current).exists())
        self.assertEqual(Portfolio.objects.count(), 0)

    def test_merge_users__dry_run_changes_nothing(self):
        """--dry-run reports what would move and leaves both accounts alone."""
        submission = baker.make(QuestSubmission, user=self.past, quest=self.quest, semester=self.semester)

        output = self.merge('--dry-run')

        submission.refresh_from_db()
        self.assertEqual(submission.user, self.past)
        self.assertTrue(User.objects.filter(pk=self.past.pk).exists())
        self.assertIn('nothing was changed', output)

    def test_merge_users__refuses_to_merge_an_account_into_itself(self):
        """Naming one account twice is a mistake, not an instruction to delete it."""
        with self.assertRaisesMessage(CommandError, 'nothing to merge'):
            self.call_command(self.past.username, self.past.username, '--noinput')

    def test_merge_users__refuses_an_unknown_username(self):
        """A typo names nobody, and says so rather than merging the wrong pair."""
        with self.assertRaisesMessage(CommandError, "No user named 'nobody'"):
            self.call_command('nobody', self.current.username, '--noinput')

    def test_merge_users__refuses_an_ambiguous_username(self):
        """Usernames differing only in case name two accounts, so the operator picks by id."""
        User.objects.create_user('PAST.student', password='password')

        with self.assertRaisesMessage(CommandError, 'matches more than one account'):
            self.call_command('past.student', self.current.username, '--noinput')

    def test_merge_users__refuses_to_delete_the_deck_owner(self):
        """The deck owner is a setting to change first: SiteConfig protects that row anyway."""
        config = SiteConfig.get()
        config.deck_owner = self.teacher
        config.save()

        with self.assertRaisesMessage(CommandError, "this deck's owner"):
            self.call_command(self.teacher.username, self.current.username, '--noinput')

    def test_merge_users__refuses_to_delete_the_decks_automation_user(self):
        """Deleting the automation user would silently repoint every automatic action."""
        config = SiteConfig.get()
        config.deck_ai = self.teacher
        config.save()

        with self.assertRaisesMessage(CommandError, 'automation user'):
            self.call_command(self.teacher.username, self.current.username, '--noinput')

    def test_merge_users__asks_for_the_source_username_before_merging(self):
        """Without --noinput the merge only goes ahead once the source username is typed back."""
        with patch('builtins.input', return_value='not-the-username'):
            with self.assertRaisesMessage(CommandError, 'did not match'):
                self.call_command(self.past.username, self.current.username)

        self.assertTrue(User.objects.filter(pk=self.past.pk).exists())

        with patch('builtins.input', return_value=self.past.username):
            self.call_command(self.past.username, self.current.username)

        self.assertFalse(User.objects.filter(pk=self.past.pk).exists())

    def test_merge_users__warns_when_the_target_would_be_in_two_open_semesters(self):
        """A student belongs to one semester, so an old registration in a second open one is flagged."""
        other_semester = baker.make(Semester, status=Semester.Status.OPEN)
        baker.make(CourseStudent, user=self.current, semester=self.semester, block=baker.make(Block))
        baker.make(CourseStudent, user=self.past, semester=other_semester, block=baker.make(Block))

        output = self.merge()

        self.assertIn('open semesters', output)

    def test_merge_users__says_the_source_profile_is_discarded(self):
        """The duplicate's alias, preferred name and settings are dropped, and the report says so."""
        output = self.merge('--dry-run')

        self.assertIn('profile', output)
        self.assertIn('is discarded', output)

    def test_merge_users__every_relation_to_user_is_handled(self):
        """Every foreign key into User is either reassigned or has a step of its own.

        A new foreign key to User that nobody taught this command about would leave rows
        pointing at the deleted account, or block the delete outright. This fails until the
        new relation is listed here and dealt with in the command.
        """
        handled_by_reassignment = {
            f'{model._meta.label}.{field}' for model, field in SIMPLE_REASSIGNMENTS
        }
        handled_by_their_own_step = {
            # The one-row-per-user tables: the target keeps its own row.
            'profile_manager.Profile.user',
            'notifications.UserNotificationOptionSet.user',
            # Its primary key is the user id, so the artwork moves instead.
            'portfolios.Portfolio.user',
            # Rebuilt rather than moved, since it is worked out from rows that just moved.
            'prerequisites.PrereqAllConditionsMet.user',
            # Moved with a check for duplicates and for who keeps the primary address.
            'account.EmailAddress.user',
            'socialaccount.SocialAccount.user',
            # Checked for collisions against the target's own registrations.
            'courses.CourseStudent.user',
            # Roles the deck cannot lose: the command refuses a source holding one.
            'siteconfig.SiteConfig.deck_owner',
            'siteconfig.SiteConfig.deck_ai',
        }

        relations = {
            f'{relation.related_model._meta.label}.{relation.field.name}'
            for relation in User._meta.related_objects
        }

        self.assertEqual(relations - handled_by_reassignment - handled_by_their_own_step, set())
