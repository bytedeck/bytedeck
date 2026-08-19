"""Regression tests for issue #2413 -- "Starting a quest while no semester is open
makes a submission nobody can see".

Work handed in by someone registered in no semester is stamped with no semester
(issue #2441 is why: the deck's default names a term they are not in). Two things
follow, and both are covered here:

* the student has to be able to see it, so the semester-scoped reads treat "no
  semester" as a semester's worth of work rather than as nothing;
* the double-start guard from #1345 has to cover it, which its constraint cannot:
  the constraint is keyed on ``(user, quest, semester)`` and Postgres treats NULLs
  as distinct, so two unstamped rows never look like duplicates to it. Migration
  0054 adds a second constraint keyed on ``(user, quest)`` for the unstamped rows,
  after deduplicating whatever a deck already has.
"""
import importlib
from unittest import mock

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from model_bakery import baker

from courses.models import Course, CourseStudent, Semester
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()

# The migration module starts with a digit, so it can't be imported with a
# plain ``import`` statement.
migration_0054 = importlib.import_module(
    "quest_manager.migrations.0054_inprogress_submission_no_semester_constraint"
)


class UnstampedSubmissionVisibilityTest(ByteDeckTenantTestCase):
    """A student between terms can see and finish the work they hand in."""

    def setUp(self):
        """Create a student whose only registration is in an archived semester, while a
        second cohort's semester keeps running: the two-cohort state from issue #2441."""
        self.student = baker.make(User, is_staff=False)
        baker.make(
            CourseStudent, user=self.student, course=baker.make(Course),
            semester=baker.make(Semester, status=Semester.Status.ARCHIVED),
        )
        self.still_running = SiteConfig.get().active_semester
        self.quest = baker.make(Quest, xp=5, published=True, archived=False, available_outside_course=True)

    def test_start__submission_is_in_the_students_own_in_progress_list(self):
        """The symptom the issue opens with: the quest looked un-started, because the
        student's in-progress list was scoped to a semester they are not in and so held
        nothing. Their list is now the work in the semester they are in, which is none."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)

        self.assertIsNone(submission.semester_id)
        self.assertIn(submission, QuestSubmission.objects.all_not_completed(user=self.student))

    def test_start__submission_reaches_the_deck_wide_approval_queue(self):
        """Somebody has to be able to approve it. No teacher's own queue holds it, since
        that queue is built from a registration and this student holds none, so the
        deck-wide queue is where it has to appear."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)
        submission.mark_completed()

        self.assertIn(submission, QuestSubmission.objects.all_awaiting_approval())

    def test_approve__xp_counts_toward_the_students_total(self):
        """Approved work that belongs to no semester still counts for the student who did
        it: their XP is what they earned in the semester they are in, and unstamped work is
        what that comes to."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)
        submission.mark_completed()
        submission.mark_approved()

        self.assertEqual(QuestSubmission.objects.calculate_xp(self.student), self.quest.xp)

    def test_completed__unstamped_work_is_current_rather_than_past(self):
        """Their past tab holds the terms behind them, not what they are doing now: the
        archived semester's work is past, and the unstamped work is current."""
        old_submission = baker.make(
            QuestSubmission, user=self.student, quest=self.quest, is_completed=True,
            semester=CourseStudent.objects.all_for_user(self.student).first().semester,
        )
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)
        submission.mark_completed()

        self.assertIn(submission, QuestSubmission.objects.all_completed(user=self.student))
        self.assertNotIn(submission, QuestSubmission.objects.all_completed_past(self.student))
        self.assertIn(old_submission, QuestSubmission.objects.all_completed_past(self.student))

    def test_start__work_is_not_attributed_to_the_cohort_still_running(self):
        """The #2441 half: the semester still running belongs to the other cohort, whose
        roster this student is absent from. Their work must not land in it, or archiving
        that cohort would drop it while recording final XP from registrations they don't
        hold."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)

        self.assertIsNotNone(self.still_running)
        self.assertNotEqual(submission.semester_id, self.still_running.id)
        self.assertNotIn(submission, QuestSubmission.objects.get_queryset().get_semester(self.still_running))


class AdoptUnstampedWorkOnRegistrationTest(ByteDeckTenantTestCase):
    """Joining a course brings the work a student had on the go into that semester."""

    def setUp(self):
        """Create an unregistered student, so what they hand in belongs to no semester, and
        the semester they are about to join."""
        self.student = baker.make(User, is_staff=False)
        self.quest = baker.make(Quest, xp=5, published=True, archived=False, available_outside_course=True)
        self.semester = SiteConfig.get().active_semester

    def register(self, user=None):
        """Register `user` (the student by default) in the semester under test."""
        return baker.make(
            CourseStudent, user=user or self.student, course=baker.make(Course), semester=self.semester,
        )

    def test_register__in_progress_work_moves_into_the_semester_joined(self):
        """The welcome-quest case: a new student starts a quest before joining a course, so
        it belongs to no semester. Joining is the moment it gains one, and without that it
        would be stranded: out of their in-progress list, which is the new semester's, and
        out of their available list, which drops a quest they already have a submission of."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)
        self.assertIsNone(submission.semester_id)

        self.register()

        submission.refresh_from_db()
        self.assertEqual(submission.semester_id, self.semester.id)
        self.assertIn(submission, QuestSubmission.objects.all_not_completed(user=self.student))

    def test_register__completed_work_stays_where_it_was_finished(self):
        """Only work still in progress moves. A quest finished outside a semester was
        finished there, so its XP belongs to no term rather than to the one being started:
        otherwise a student could bank XP between terms and cash it in on the next one."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)
        submission.mark_completed()

        self.register()

        submission.refresh_from_db()
        self.assertIsNone(submission.semester_id)

    def test_register__work_of_an_archived_quest_moves_too(self):
        """A quest archived while the student had it on the go is still theirs to finish, so
        it moves with the rest rather than being left behind by a manager that hides it."""
        archived_quest = baker.make(Quest, published=True, archived=False)
        submission = QuestSubmission.objects.create_submission(self.student, archived_quest)
        archived_quest.archived = True
        archived_quest.save()

        self.register()

        submission.refresh_from_db()
        self.assertEqual(submission.semester_id, self.semester.id)

    def test_register__leaves_work_that_would_collide_with_the_semesters_own(self):
        """A student who was in this semester before, left it, and is registering again can
        hold both a submission of a quest stamped with it and an unstamped one. Only one
        never-completed in-progress submission per quest and semester is allowed, so the
        unstamped one stays where it is rather than breaking that rule."""
        stamped = baker.make(
            QuestSubmission, user=self.student, quest=self.quest, semester=self.semester,
            is_completed=False,
        )
        unstamped = baker.make(
            QuestSubmission, user=self.student, quest=self.quest, semester=None, is_completed=False,
        )

        self.register()

        unstamped.refresh_from_db()
        stamped.refresh_from_db()
        self.assertIsNone(unstamped.semester_id)
        self.assertEqual(stamped.semester_id, self.semester.id)

    def test_register__another_students_work_is_left_alone(self):
        """One student joining a course says nothing about anyone else's work."""
        classmate = baker.make(User, is_staff=False)
        theirs = QuestSubmission.objects.create_submission(classmate, self.quest)

        self.register()

        theirs.refresh_from_db()
        self.assertIsNone(theirs.semester_id)

    def test_register__into_a_semester_that_is_not_open_moves_nothing(self):
        """A registration in a semester that has not started (or is over) is not a semester
        the student is earning in yet, so there is nothing for their work to join."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)

        baker.make(
            CourseStudent, user=self.student, course=baker.make(Course),
            semester=baker.make(Semester, status=Semester.Status.UPCOMING),
        )

        submission.refresh_from_db()
        self.assertIsNone(submission.semester_id)

    def test_register__editing_a_registration_later_moves_nothing(self):
        """Only joining brings work along. Saving an existing registration again (a teacher
        making an XP adjustment, say) must not sweep up whatever the student has done outside
        a semester since."""
        registration = self.register()
        later = QuestSubmission.objects.create_submission(self.student, baker.make(Quest, published=True))
        # they left the semester after starting it, which is how the work came to be unstamped
        QuestSubmission._base_manager.filter(pk=later.pk).update(semester=None)

        registration.xp_adjustment = 10
        registration.save()

        later.refresh_from_db()
        self.assertIsNone(later.semester_id)


class AdoptUnstampedWorkOnSemesterOpenTest(ByteDeckTenantTestCase):
    """Opening a semester brings its students' on-the-go work into it (issue #2476)."""

    def setUp(self):
        """Create a semester that has not started and a student registered in it, the shape a
        teacher gets by signing a cohort up ahead of the term through the admin."""
        self.student = baker.make(User, is_staff=False)
        self.quest = baker.make(Quest, xp=5, published=True, archived=False, available_outside_course=True)
        self.semester = baker.make(Semester, status=Semester.Status.UPCOMING)
        baker.make(CourseStudent, user=self.student, course=baker.make(Course), semester=self.semester)

    def open_semester(self):
        """Start the semester under test, the way the admin does."""
        self.semester.status = Semester.Status.OPEN
        self.semester.save()

    def test_open__in_progress_work_of_a_registered_student_moves_into_the_semester(self):
        """A student signed up before their term starts holds no open registration, so they
        can do the quests marked available outside a course and what they hand in belongs to
        no semester. Opening their semester is the moment that work gains one. Without it the
        work is stranded: out of the in-progress list, which is now their semester's, and out
        of the available list, which drops a quest they already have a submission of."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)
        self.assertIsNone(submission.semester_id)

        self.open_semester()

        submission.refresh_from_db()
        self.assertEqual(submission.semester_id, self.semester.id)
        self.assertIn(submission, QuestSubmission.objects.all_not_completed(user=self.student))

    def test_open__one_students_collision_does_not_hold_back_a_classmates_work(self):
        """A whole cohort moves at once, so the rule that a student cannot hold two
        never-completed submissions of one quest in a semester is checked per student. A
        classmate who already has that quest on the go in this semester keeps their unstamped
        one where it is, and that says nothing about anybody else's submission of it."""
        classmate = baker.make(User, is_staff=False)
        baker.make(CourseStudent, user=classmate, course=baker.make(Course), semester=self.semester)
        baker.make(
            QuestSubmission, user=classmate, quest=self.quest, semester=self.semester, is_completed=False,
        )
        theirs = baker.make(
            QuestSubmission, user=classmate, quest=self.quest, semester=None, is_completed=False,
        )
        mine = QuestSubmission.objects.create_submission(self.student, self.quest)

        self.open_semester()

        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertEqual(mine.semester_id, self.semester.id)
        self.assertIsNone(theirs.semester_id)

    def test_open__completed_work_stays_where_it_was_finished(self):
        """Only work still in progress moves, the same rule joining a course follows: a quest
        finished outside a semester was finished there, so its XP belongs to no term rather
        than to the one about to start."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)
        submission.mark_completed()

        self.open_semester()

        submission.refresh_from_db()
        self.assertIsNone(submission.semester_id)

    def test_open__work_of_a_student_registered_elsewhere_is_left_alone(self):
        """Opening one semester says nothing about the students who are not in it. A deck can
        run two cohorts on different calendars (issue #1781), so someone waiting on the other
        term keeps their work unstamped until that term opens."""
        outsider = baker.make(User, is_staff=False)
        theirs = QuestSubmission.objects.create_submission(outsider, self.quest)

        self.open_semester()

        theirs.refresh_from_db()
        self.assertIsNone(theirs.semester_id)

    def test_set_active_semester__adopts_the_work_of_the_students_it_starts(self):
        """Starting a semester through the deck's own action is the path a teacher actually
        takes, so it has to adopt as well as a direct status edit in the admin does."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)

        SiteConfig.get().set_active_semester(self.semester)

        submission.refresh_from_db()
        self.assertEqual(submission.semester_id, self.semester.id)

    def test_open__saving_the_semester_again_disturbs_nothing(self):
        """Adoption runs on any save that leaves the semester open, not only on the one that
        opens it, because a semester can be started from the admin as well as through the
        deck's action. Saving an open semester again therefore has to leave the work it
        already adopted where it is."""
        submission = QuestSubmission.objects.create_submission(self.student, self.quest)
        self.open_semester()

        self.semester.name = 'Renamed after it started'
        self.semester.save()

        submission.refresh_from_db()
        self.assertEqual(submission.semester_id, self.semester.id)


class UnstampedDoubleStartRaceTest(ByteDeckTenantTestCase):
    """The #1345 double-start race, for the submissions that name no semester."""

    def setUp(self):
        """Create an unregistered student (so their work is unstamped) and a
        non-repeatable published quest."""
        self.student = baker.make(User, is_staff=False)
        self.quest = baker.make(
            Quest, name="One-time quest", xp=10,
            max_repeats=0, repeat_per_semester=False,
            published=True, archived=False,
        )

    def test_save__second_fresh_unstamped_submission_raises_integrity_error(self):
        """The DB-level guard: a second never-completed in-progress submission of the same
        quest with no semester is refused, which the constraint keyed on the semester could
        not do, since Postgres compares NULLs as distinct."""
        first = QuestSubmission.objects.create_submission(self.student, self.quest)
        self.assertIsNone(first.semester_id)

        duplicate = QuestSubmission(quest=self.quest, user=self.student, ordinal=2, semester=None)
        with self.assertRaises(IntegrityError):
            # Wrapped so the failed statement doesn't poison the test transaction.
            with transaction.atomic():
                # Constraint validation skipped so the DB constraint itself
                # (the behaviour under test) raises, not full_clean.
                duplicate.full_clean(validate_constraints=False)
                duplicate.save()

    def test_mark_returned__allowed_while_new_unstamped_submission_in_progress(self):
        """The exemption carries over: a teacher returning an old submission while a new
        one is in progress leaves two in-progress rows with no semester, and only one of
        them was never completed, so the constraint stays out of the way."""
        repeatable = baker.make(Quest, max_repeats=-1, published=True, archived=False)
        first = QuestSubmission.objects.create_submission(self.student, repeatable)
        first.mark_completed()
        first.mark_approved()
        second = QuestSubmission.objects.create_submission(self.student, repeatable)

        first.mark_returned()

        first.refresh_from_db()
        self.assertIsNotNone(first.first_time_completed)  # what exempts it
        self.assertIsNone(second.semester_id)
        self.assertEqual(
            QuestSubmission.objects.filter(user=self.student, quest=repeatable, is_completed=False).count(), 2,
        )


class MigrationDedupTest(ByteDeckTenantTestCase):
    """Cover migration 0054's ``remove_duplicate_unstamped_in_progress_submissions``:
    it must delete duplicate never-completed in-progress rows that name no semester
    (keeping the earliest, flushing deletes in bounded batches) and spare completed,
    returned, and stamped rows."""

    # Drops and re-adds the QuestSubmission unique constraint via the schema
    # editor, so give it a private fresh schema rather than mutating the shared
    # reused one (and to avoid colliding with the persistent test tenant).
    reuse_schema = False

    def _constraint(self):
        """Return the no-semester partial unique constraint object from QuestSubmission's
        Meta, so tests can drop and re-add it via the schema editor."""
        return next(
            c for c in QuestSubmission._meta.constraints
            if c.name == "unique_inprogress_submission_per_quest_no_semester"
        )

    def _run_dedup(self):
        """Invoke the migration's dedup function against the current (test)
        schema, exactly as RunPython would."""
        with connection.schema_editor() as schema_editor:
            migration_0054.remove_duplicate_unstamped_in_progress_submissions(
                django_apps, schema_editor,
            )

    def test_remove_duplicate_unstamped_in_progress_submissions__removes_duplicates_spares_rest(self):
        """Duplicate fresh in-progress rows with no semester (what a deck can already hold,
        since 0049's dedup left them alone) are deleted keeping the earliest -- in bounded
        batches -- while completed, returned, and stamped rows survive."""
        student = baker.make(User, is_staff=False)
        quest = baker.make(Quest, published=True, archived=False)

        # Recreate the pre-constraint state by dropping the constraint first.
        with connection.schema_editor() as schema_editor:
            schema_editor.remove_constraint(QuestSubmission, self._constraint())
        try:
            keeper = baker.make(
                QuestSubmission, user=student, quest=quest, semester=None, is_completed=False,
            )
            # Three duplicates + a batch size of 2 (patched below) exercises both
            # the mid-loop batch flush and the final leftover flush.
            duplicates = baker.make(
                QuestSubmission, user=student, quest=quest, semester=None,
                is_completed=False, _quantity=3,
            )
            completed = baker.make(
                QuestSubmission, user=student, quest=quest, semester=None, is_completed=True,
            )
            # A *returned* submission (in progress again, but first_time_completed
            # set) must be skipped by the dedup even alongside a fresh in-progress
            # row -- it's exempt from the constraint.
            returned = baker.make(
                QuestSubmission, user=student, quest=quest, semester=None,
                is_completed=False, first_time_completed=timezone.now(),
            )
            # A row that names a semester is 0049's business, not this dedup's.
            stamped = baker.make(
                QuestSubmission, user=student, quest=quest,
                semester=SiteConfig.get().active_semester, is_completed=False,
            )

            with mock.patch.object(migration_0054, "DEDUP_BATCH_SIZE", 2):
                self._run_dedup()

            self.assertTrue(QuestSubmission.objects.filter(pk=keeper.pk).exists())
            for duplicate in duplicates:
                self.assertFalse(QuestSubmission.objects.filter(pk=duplicate.pk).exists())
            self.assertTrue(QuestSubmission.objects.filter(pk=completed.pk).exists())
            self.assertTrue(QuestSubmission.objects.filter(pk=returned.pk).exists())
            self.assertTrue(QuestSubmission.objects.filter(pk=stamped.pk).exists())
        finally:
            # The dedup's deletes leave deferred trigger events pending in the
            # test transaction, and Postgres refuses CREATE INDEX while they
            # exist -- force them to fire before re-adding the constraint.
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            with connection.schema_editor() as schema_editor:
                schema_editor.add_constraint(QuestSubmission, self._constraint())

    def test_remove_duplicate_unstamped_in_progress_submissions__noop_when_no_duplicates(self):
        """With no duplicate rows the dedup deletes nothing (the empty branch)."""
        student = baker.make(User, is_staff=False)
        quest = baker.make(Quest, published=True, archived=False)
        sub = QuestSubmission.objects.create_submission(student, quest)

        self._run_dedup()

        self.assertTrue(QuestSubmission.objects.filter(pk=sub.pk).exists())
