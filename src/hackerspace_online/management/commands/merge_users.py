"""Fold one user account into another, within a single deck's schema.

Two accounts for the same person happen: a student signs up again instead of signing in, or
carries an account over from a previous year under a new username. This moves everything the
duplicate owns onto the account being kept, then deletes the duplicate.
"""

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount

from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from announcements.models import Announcement
from badges.models import BadgeAssertion
from comments.models import Comment
from courses.models import Block, CourseStudent, Semester
from notifications.models import Notification, UserNotificationOptionSet
from portfolios.models import Artwork, Portfolio
from prerequisites.models import PrereqAllConditionsMet
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()

# Every foreign key into User that a plain rewrite settles, as (model, field name). The
# relations left out of this list are the ones that need a decision rather than a rewrite:
# the one-row-per-user tables, the portfolio (whose primary key is the user id), the
# prerequisite cache, and the sign-in records. Each has its own step below.
#
# Keep this in step with `User._meta.related_objects`: a new foreign key to User belongs
# either here or in a step of its own, and `test_merge_users__every_relation_to_user_is_handled`
# fails until it is in one of them.
SIMPLE_REASSIGNMENTS = (
    (Announcement, 'author'),
    (BadgeAssertion, 'user'),
    (BadgeAssertion, 'issued_by'),
    (Block, 'current_teacher'),
    (Comment, 'user'),
    (LogEntry, 'user'),
    (Notification, 'recipient'),
    (Quest, 'editor'),
    (Quest, 'specific_teacher_to_notify'),
    (QuestSubmission, 'user'),
    (QuestSubmission, 'flagged_by'),
)

# The generic foreign keys that can hold a user. A notification names its sender that way,
# and the action and target slots are included because the same three columns are filled from
# whatever a caller passes. Comment.target_object is a submission or an announcement today,
# and is rewritten anyway so that a future target of a user does not quietly survive the merge.
# The generic keys on Prereq and CytoScape are left out: they address quests, badges, campaigns
# and ranks, and a user is not a valid value for any of them.
GENERIC_USER_REFERENCES = (
    (Notification, 'sender_content_type', 'sender_object_id'),
    (Notification, 'action_content_type', 'action_object_id'),
    (Notification, 'target_content_type', 'target_object_id'),
    (Comment, 'target_content_type', 'target_object_id'),
)


class Command(BaseCommand):
    """Move everything one user owns onto another user, then delete the emptied account."""

    help = (
        "Merge one user account into another within a deck. Everything the source account owns "
        "(quest submissions, badges, course registrations, comments, notifications, portfolio "
        "artwork) moves to the target account, and the source account is then deleted. "
        "Run it per deck: manage.py tenant_command merge_users --schema=<deck> <source> <target>"
    )

    def add_arguments(self, parser):
        """Take the two accounts and the flags that decide how far the command goes.

        Args:
            parser (ArgumentParser): the command's own parser.
        """
        parser.add_argument(
            'source',
            help="Username (or id, with --by-id) of the duplicate account. It is deleted.",
        )
        parser.add_argument(
            'target',
            help="Username (or id, with --by-id) of the account to keep. Everything ends up here.",
        )
        parser.add_argument(
            '--by-id',
            action='store_true',
            help="Read source and target as user ids rather than usernames.",
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help="Report what would move and stop without changing anything.",
        )
        parser.add_argument(
            '--noinput', '--no-input',
            action='store_false',
            dest='interactive',
            help="Do not ask for confirmation before merging.",
        )

    def handle(self, *args, **options):
        """Check the merge is safe, report what it moves, then carry it out.

        Args:
            *args: unused.
            **options: the parsed arguments.

        Raises:
            CommandError: when either account cannot be found, they are the same account, the
                source holds a role the deck cannot lose, or the operator declines at the prompt.
        """
        source = self.get_user(options['source'], by_id=options['by_id'])
        target = self.get_user(options['target'], by_id=options['by_id'])

        if source.pk == target.pk:
            raise CommandError("Source and target are the same account, so there is nothing to merge.")

        self.refuse_a_source_the_deck_needs(source)

        self.stdout.write(f"Merging {self.describe(source)}")
        self.stdout.write(f"   into {self.describe(target)}")
        self.stdout.write('')

        self.report_what_moves(source)
        warnings = self.collect_warnings(source, target)
        for warning in warnings:
            self.stdout.write(self.style.WARNING(f"  ! {warning}"))
        self.stdout.write('')

        if options['dry_run']:
            self.stdout.write(self.style.NOTICE("Dry run: nothing was changed."))
            return

        if options['interactive']:
            self.stdout.write(self.style.WARNING(
                f"This deletes {source.username} and cannot be undone. Restoring it means restoring a backup."
            ))
            if input("Type the source username to go ahead: ").strip() != source.username:
                raise CommandError("That did not match the source username, so nothing was changed.")

        self.merge(source, target)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"Merged into {target.username} (id {target.pk}). {source.username} has been deleted."
        ))
        target.profile.refresh_from_db()
        self.stdout.write(f"{target.username} now has {target.profile.xp_cached} XP.")

    def get_user(self, identifier, by_id=False):
        """Find one account by username or id.

        Usernames are matched without regard to case, since a deck can hold accounts that
        differ only in case (see the lowercase_usernames command).

        Args:
            identifier (str): the username or id typed on the command line.
            by_id (bool): True to read the identifier as a primary key.

        Returns:
            User: the matching account.

        Raises:
            CommandError: when nothing matches, or when a username matches more than one account.
        """
        if by_id:
            try:
                return User.objects.get(pk=identifier)
            except (User.DoesNotExist, ValueError):
                raise CommandError(f"No user with id {identifier!r} in this deck.")

        matches = list(User.objects.filter(username__iexact=identifier))
        if not matches:
            raise CommandError(f"No user named {identifier!r} in this deck.")
        if len(matches) > 1:
            ids = ', '.join(str(user.pk) for user in matches)
            raise CommandError(
                f"{identifier!r} matches more than one account (ids: {ids}). Name it with --by-id."
            )
        return matches[0]

    def describe(self, user):
        """Write one line naming an account, so the operator can see they picked the right one.

        Args:
            user (User): the account to describe.

        Returns:
            str: the username, id, full name and XP.
        """
        profile = getattr(user, 'profile', None)
        xp = profile.xp_cached if profile else 'no profile'
        return f"{user.username} (id {user.pk}, {user.get_full_name() or 'no name'}, {xp} XP)"

    def refuse_a_source_the_deck_needs(self, source):
        """Stop before deleting an account the deck points at.

        SiteConfig holds the deck owner under a PROTECT foreign key and the automation user
        under SET_DEFAULT, so deleting either would fail outright or silently repoint the
        deck's automation. Both are settings to change first, by hand, rather than as part
        of a merge.

        Args:
            source (User): the account that would be deleted.

        Raises:
            CommandError: when the source is the deck owner or the deck's automation user.
        """
        config = SiteConfig.get()
        if config.deck_owner_id == source.pk:
            raise CommandError(
                f"{source.username} is this deck's owner. Hand the deck over in Site Config first."
            )
        if config.deck_ai_id == source.pk:
            raise CommandError(
                f"{source.username} is this deck's automation user ('{config.deck_ai}'). "
                "Point Site Config at another staff user first."
            )

    def report_what_moves(self, source):
        """Print a count for everything the source account owns.

        Args:
            source (User): the account being merged away.
        """
        self.stdout.write("Moving:")
        for model, field in SIMPLE_REASSIGNMENTS:
            count = model.objects.filter(**{field: source}).count()
            if count:
                self.stdout.write(f"  {count:>5}  {model._meta.label}.{field}")

        for model, content_type_field, object_id_field in GENERIC_USER_REFERENCES:
            count = self.generic_references(model, content_type_field, object_id_field, source).count()
            if count:
                self.stdout.write(f"  {count:>5}  {model._meta.label}.{content_type_field[:-13]}_object")

        registrations = CourseStudent.objects.filter(user=source).count()
        if registrations:
            self.stdout.write(f"  {registrations:>5}  courses.CourseStudent.user")

        artwork = Artwork.objects.filter(portfolio__user=source).count()
        if artwork:
            self.stdout.write(f"  {artwork:>5}  portfolios.Artwork (onto the target's portfolio)")

        emails = EmailAddress.objects.filter(user=source).count()
        socials = SocialAccount.objects.filter(user=source).count()
        if emails:
            self.stdout.write(f"  {emails:>5}  account.EmailAddress (as non-primary addresses)")
        if socials:
            self.stdout.write(f"  {socials:>5}  socialaccount.SocialAccount")
        self.stdout.write('')

    def collect_warnings(self, source, target):
        """Work out what the merge will drop or leave in an odd state, so it is said up front.

        Args:
            source (User): the account being merged away.
            target (User): the account being kept.

        Returns:
            list: one string per thing worth knowing before going ahead.
        """
        warnings = []

        for registration in self.colliding_registrations(source, target):
            warnings.append(
                f"Course registration '{registration}' duplicates one {target.username} already has; "
                f"it will be dropped rather than moved.{self.what_a_registration_carries(registration)}"
            )

        semesters = self.open_semesters_after_merge(source, target)
        if len(semesters) > 1:
            names = ', '.join(str(semester) for semester in semesters)
            warnings.append(
                f"{target.username} would be registered in {len(semesters)} open semesters ({names}). "
                "A student belongs to one: close one, or move the registration, once the merge is done."
            )

        for submission in self.colliding_submissions(source, target):
            warnings.append(
                f"In-progress submission of '{submission.quest}' duplicates one {target.username} "
                "already has in the same semester; it will be dropped rather than moved."
            )

        # Every account in a deck has a profile: one is created with the user (see
        # profile_manager.models.create_profile), so this is always worth saying.
        warnings.append(
            f"{source.username}'s profile (alias, preferred name, avatar, settings) is discarded. "
            f"{target.username} keeps their own."
        )

        for email in EmailAddress.objects.filter(user=source):
            if EmailAddress.objects.filter(user=target, email__iexact=email.email).exists():
                warnings.append(f"Email address {email.email} is already on {target.username}; it will be dropped.")

        return warnings

    def generic_references(self, model, content_type_field, object_id_field, user):
        """Select the rows whose generic foreign key addresses this user.

        Args:
            model (Model): the model holding the generic foreign key.
            content_type_field (str): name of its content type column.
            object_id_field (str): name of its object id column.
            user (User): the user being addressed.

        Returns:
            QuerySet: the matching rows.
        """
        user_type = ContentType.objects.get_for_model(User)
        return model.objects.filter(**{
            content_type_field: user_type,
            object_id_field: user.pk,
        })

    def what_a_registration_carries(self, registration):
        """Name the numbers on a registration that go when it is dropped.

        A registration is not only a place in a group: it can hold a one-time XP adjustment a
        teacher gave the student, and the final XP and grade recorded when its semester was
        archived. Those are the student's, not the slot's, so an operator deciding whether to
        go ahead needs to see them rather than read them off the string form, which shows the
        username, semester, group and course and nothing else.

        Args:
            registration (CourseStudent): the registration about to be dropped.

        Returns:
            str: a sentence naming what it carries, or '' when it carries none of it.
        """
        carried = []
        if registration.xp_adjustment:
            carried.append(f"an XP adjustment of {registration.xp_adjustment}")
        if registration.final_xp is not None or registration.final_grade is not None:
            carried.append(f"final marks ({registration.final_xp} XP, {registration.final_grade}%)")

        if not carried:
            return ''
        return f" It carries {' and '.join(carried)}, which goes with it."

    def colliding_registrations(self, source, target):
        """Find the source's course registrations the target already has.

        CourseStudent is unique on (semester, block, user) and on (user, course, grade_fk), so
        a registration matching either of those on the target cannot be moved.

        Matching on one of those pairs does not make the two rows identical: a row matching on
        (semester, block) can name a different course, and one matching on (course, grade_fk)
        can belong to a different semester, an archived one carrying final marks. Either can
        hold its own xp_adjustment. What the dropped row takes with it is named in the report
        (see what_a_registration_carries) so it is a decision rather than a surprise.

        Args:
            source (User): the account being merged away.
            target (User): the account being kept.

        Returns:
            list: the source registrations that cannot move.
        """
        # A key holding a null is not a collision: Postgres counts nulls as distinct, so a
        # registration naming no group or no course never clashes with another one.
        held_by_target = CourseStudent.objects.filter(user=target)
        slots = {
            (registration.semester_id, registration.block_id) for registration in held_by_target
            if registration.semester_id is not None and registration.block_id is not None
        }
        courses = {
            (registration.course_id, registration.grade_fk_id) for registration in held_by_target
            if registration.course_id is not None and registration.grade_fk_id is not None
        }

        return [
            registration for registration in CourseStudent.objects.filter(user=source)
            if (registration.semester_id, registration.block_id) in slots
            or (registration.course_id, registration.grade_fk_id) in courses
        ]

    def open_semesters_after_merge(self, source, target):
        """List the open semesters the target would be registered in once the merge is done.

        A student belongs to one semester (see CourseStudent.clean), and the merge rewrites
        registrations with an update that does not run that check, so this reports the state
        instead of refusing it: the operator decides what to do with an old registration that
        turns out to be in a semester still open.

        Args:
            source (User): the account being merged away.
            target (User): the account being kept.

        Returns:
            list: the distinct open semesters, in id order.
        """
        registrations = CourseStudent.objects.filter(user__in=[source, target]).exclude(semester=None)
        semester_ids = set(registrations.values_list('semester_id', flat=True))
        return list(
            Semester.objects.filter(pk__in=semester_ids, status=Semester.Status.OPEN).order_by('pk')
        )

    def colliding_submissions(self, source, target):
        """Find the source's in-progress submissions the target already has one of.

        QuestSubmission refuses a second never-yet-completed submission of the same quest in
        the same semester, so those rows cannot be moved. They carry no work that was handed
        in, which is why dropping one is a note rather than a refusal.

        Args:
            source (User): the account being merged away.
            target (User): the account being kept.

        Returns:
            list: the source submissions that cannot move.
        """
        in_progress = QuestSubmission.objects.filter(is_completed=False, first_time_completed__isnull=True)
        held_by_target = {
            (submission.quest_id, submission.semester_id)
            for submission in in_progress.filter(user=target)
        }
        return [
            submission for submission in in_progress.filter(user=source)
            if (submission.quest_id, submission.semester_id) in held_by_target
        ]

    @transaction.atomic
    def merge(self, source, target):
        """Move everything from one account to the other and delete the emptied one.

        Every step runs in one transaction, so a failure part way leaves both accounts as
        they were.

        Args:
            source (User): the account being merged away.
            target (User): the account being kept.
        """
        # The rows that cannot move go first, while they can still be told apart by owner.
        for registration in self.colliding_registrations(source, target):
            registration.delete()
        for submission in self.colliding_submissions(source, target):
            submission.delete()

        CourseStudent.objects.filter(user=source).update(user=target)

        for model, field in SIMPLE_REASSIGNMENTS:
            model.objects.filter(**{field: source}).update(**{field: target})

        for model, content_type_field, object_id_field in GENERIC_USER_REFERENCES:
            self.generic_references(model, content_type_field, object_id_field, source).update(
                **{object_id_field: target.pk}
            )

        self.move_portfolio(source, target)
        self.move_sign_in_records(source, target)

        target.groups.add(*source.groups.all())
        target.user_permissions.add(*source.user_permissions.all())

        # One row per user, and the target keeps its own, so the source's is dropped rather
        # than moved. Deleting the user would take it anyway; doing it here keeps the whole
        # merge readable as a list of decisions.
        UserNotificationOptionSet.objects.filter(user=source).delete()

        # The cache of which quests a user can see is worked out from their submissions and
        # badges, both of which just moved, so both users' rows are stale. The target's is
        # rebuilt below, once the source is gone.
        PrereqAllConditionsMet.objects.filter(user__in=[source, target]).delete()

        source.delete()

        self.renumber_ordinals(target)
        self.rebuild_caches(target)

    def move_portfolio(self, source, target):
        """Move the source's artwork onto the target's portfolio.

        A Portfolio's primary key is its user id, so it cannot be reassigned: the artwork moves
        instead, and the emptied portfolio goes with the user. The target is given a portfolio
        if they never opened one, so artwork is never dropped for want of somewhere to put it.
        The source's portfolio description and its listed_locally / listed_publicly settings are
        not carried over, since the target's own settings say who may see the merged portfolio.

        Args:
            source (User): the account being merged away.
            target (User): the account being kept.
        """
        source_portfolio = Portfolio.objects.filter(user=source).first()
        if source_portfolio is None:
            return

        if Artwork.objects.filter(portfolio=source_portfolio).exists():
            target_portfolio, _ = Portfolio.objects.get_or_create(user=target)
            Artwork.objects.filter(portfolio=source_portfolio).update(portfolio=target_portfolio)

        source_portfolio.delete()

    def move_sign_in_records(self, source, target):
        """Carry the source's ways of signing in over to the target.

        A social account moves as it is, so signing in with the Google account that used to
        reach the duplicate now reaches the merged account. An email address moves only when
        the target does not already have it, and always as a non-primary address, so the
        target keeps the address the deck writes to. Addresses beyond what allauth allows per
        account (ACCOUNT_MAX_EMAIL_ADDRESSES) are dropped, as is any duplicate.

        Args:
            source (User): the account being merged away.
            target (User): the account being kept.

        Raises:
            ValidationError: when a stored address does not validate, which stops the merge
                with nothing applied rather than carrying a bad row onto the kept account.
        """
        SocialAccount.objects.filter(user=source).update(user=target)

        limit = getattr(settings, 'ACCOUNT_MAX_EMAIL_ADDRESSES', None)
        for email in EmailAddress.objects.filter(user=source):
            already_there = EmailAddress.objects.filter(user=target, email__iexact=email.email).exists()
            room_left = limit is None or EmailAddress.objects.filter(user=target).count() < limit
            if already_there or not room_left:
                email.delete()
                continue
            email.user = target
            email.primary = False
            email.full_clean()
            email.save()

    def renumber_ordinals(self, target):
        """Number the target's repeated submissions and badges 1, 2, 3 again.

        Both models count repeats with an ordinal held per user, and each account was numbering
        from one of its own, so merging leaves two rows sharing a number. The count of how many
        times a quest was done or a badge earned reads the highest ordinal, which would come out
        short until they are renumbered in the order they happened.

        Args:
            target (User): the account that now holds both sets of rows.
        """
        for quest_id in QuestSubmission.objects.filter(user=target).values_list('quest_id', flat=True).distinct():
            submissions = QuestSubmission.objects.filter(user=target, quest_id=quest_id).order_by('timestamp', 'pk')
            for ordinal, submission in enumerate(submissions, start=1):
                if submission.ordinal != ordinal:
                    QuestSubmission.objects.filter(pk=submission.pk).update(ordinal=ordinal)

        for badge_id in BadgeAssertion.objects.filter(user=target).values_list('badge_id', flat=True).distinct():
            assertions = BadgeAssertion.objects.filter(user=target, badge_id=badge_id).order_by('timestamp', 'pk')
            for ordinal, assertion in enumerate(assertions, start=1):
                if assertion.ordinal != ordinal:
                    BadgeAssertion.objects.filter(pk=assertion.pk).update(ordinal=ordinal)

    def rebuild_caches(self, target):
        """Work out the target's XP, mark and available quests again.

        The merge moves rows with updates, which do not fire the signals that normally keep
        these up to date, so both caches are rebuilt here rather than left for the nightly
        task. The quest cache is rebuilt in this process rather than queued, so the command
        leaves nothing waiting on a celery worker that may not be running.

        Args:
            target (User): the account that now holds everything.
        """
        from prerequisites.tasks import update_quest_conditions_for_user

        target.profile.xp_invalidate_cache()
        update_quest_conditions_for_user.apply(args=[target.pk])
