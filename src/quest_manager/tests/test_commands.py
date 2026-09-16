from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from model_bakery import baker

from courses.models import Course, CourseStudent, Rank
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from prerequisites.models import Prereq, PrereqAllConditionsMet
from quest_manager.management.commands.quest_availability import Command as QuestAvailabilityCommand
from quest_manager.models import Quest, QuestSubmission
from siteconfig.models import SiteConfig

User = get_user_model()


class QuestAvailabilityCommandTest(ByteDeckTenantTestCase):
    """The command that explains why a quest is, or is not, in a student's Available tab.

    The tab and "can I start this?" are two different code paths, so a quest can be missing from
    the list while opening perfectly from the quest map. The command exists to say which of the
    tab's filters accounts for that, rather than leaving it to be guessed at.
    """

    def setUp(self):
        """A student registered this semester, and a quest they qualify for."""
        self.student = baker.make(User, username="test.student")
        baker.make(CourseStudent, user=self.student, course=baker.make(Course),
                   semester=SiteConfig.get().active_semester)
        self.quest = baker.make(Quest, name="Pixel Art 1. Introduction", blocking=False)

    def run_command(self, *args):
        """Run the command and hand back what it printed.

        Args:
            *args: the command's arguments, starting with the username.

        Returns:
            str: everything written to stdout.
        """
        out = StringIO()
        call_command('quest_availability', *args, stdout=out)
        return out.getvalue()

    def cache_ids(self):
        """The quest ids currently stored as this student's met prerequisites.

        Returns:
            set[int]: the cached ids, empty when they have no cache row.
        """
        row = PrereqAllConditionsMet.objects.filter(
            user=self.student, model_name=Quest.get_model_name()).first()
        return set(row.get_ids()) if row else set()

    # Looking things up ###################################################

    def test_quest_availability__unknown_user_is_an_error(self):
        """A username that is not on this deck is worth saying plainly: the usual cause is the
        command being pointed at the wrong schema."""
        with self.assertRaises(CommandError) as raised:
            self.run_command("nobody.here")

        self.assertIn("--schema", str(raised.exception))

    def test_quest_availability__quest_by_id(self):
        """A quest can be named by its id, which is what the summary tells you to use."""
        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn(f"Quest:   {self.quest.name} (id {self.quest.id})", output)

    def test_quest_availability__unknown_quest_id_is_an_error(self):
        """An id with no quest behind it stops rather than reporting on nothing."""
        with self.assertRaises(CommandError) as raised:
            self.run_command("test.student", "--quest", "999999")

        self.assertIn("999999", str(raised.exception))

    def test_quest_availability__quest_by_name(self):
        """Part of a name is enough, since that is what a teacher has to hand."""
        output = self.run_command("test.student", "--quest", "Pixel Art")

        self.assertIn(f"(id {self.quest.id})", output)

    def test_quest_availability__unknown_quest_name_is_an_error(self):
        """A name matching nothing stops, rather than silently reporting on some other quest."""
        with self.assertRaises(CommandError) as raised:
            self.run_command("test.student", "--quest", "no such quest")

        self.assertIn("no such quest", str(raised.exception))

    def test_quest_availability__an_ambiguous_name_lists_the_candidates(self):
        """Several matches are listed with their ids, so the next run can name one."""
        baker.make(Quest, name="Pixel Art 2. Colour")

        with self.assertRaises(CommandError) as raised:
            self.run_command("test.student", "--quest", "Pixel Art")

        self.assertIn("matches several quests", str(raised.exception))
        self.assertIn(str(self.quest.id), str(raised.exception))

    def test_quest_availability__reports_on_an_archived_quest_too(self):
        """A quest archived out from under a student is exactly what this is asked about, so it
        is not excluded from the lookup."""
        self.quest.archived = True
        self.quest.save()

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn(f"(id {self.quest.id})", output)

    # The cache ###########################################################

    def test_quest_availability__no_cache_row_is_not_stale(self):
        """With nothing stored the tab computes the answer on demand, so there is nothing to be
        out of date."""
        PrereqAllConditionsMet.objects.filter(user=self.student).delete()

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("none stored", output)

    def test_quest_availability__an_accurate_cache_is_reported_as_up_to_date(self):
        """The ordinary case says so in one line, so a stale one stands out."""
        Quest.objects.get_available(self.student)  # builds the cache, as loading the tab does

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("up to date", output)

    def test_quest_availability__a_cache_missing_a_quest_is_reported_as_stale(self):
        """A quest the student qualifies for but the cache still calls locked is the shape of the
        bug this exists for: invisible in the tab, startable from the map."""
        Quest.objects.get_available(self.student)
        PrereqAllConditionsMet.objects.filter(user=self.student).update(ids='[]')

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("STALE", output)
        self.assertIn("they now qualify for are missing from it", output)

    def test_quest_availability__a_cache_holding_too_much_is_reported_as_stale(self):
        """The other direction matters too: a quest they no longer qualify for still being
        offered is just as wrong, and just as permanent."""
        Quest.objects.get_available(self.student)
        # everything they really do qualify for, plus one they do not, so only the second half
        # of the staleness report has anything to say
        stored = sorted(self.cache_ids() | {999999})
        PrereqAllConditionsMet.objects.filter(user=self.student).update(ids=str(stored))

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("STALE", output)
        self.assertIn("they no longer qualify for are still in it", output)
        self.assertNotIn("they now qualify for are missing from it", output)

    def test_quest_availability__rebuild_recomputes_the_cache_in_process(self):
        """--rebuild does the work here rather than queueing it, which is what makes it usable
        while celery is down: that is when the cache goes stale and stays stale."""
        Quest.objects.get_available(self.student)
        PrereqAllConditionsMet.objects.filter(user=self.student).update(ids='[]')

        output = self.run_command("test.student", "--rebuild")

        self.assertIn("Rebuilt the cache", output)
        self.assertIn(self.quest.id, self.cache_ids())

    # Accounting for one quest ############################################

    def test_quest_availability__a_listed_quest_is_reported_as_listed(self):
        """A quest that really is in the tab gets a verdict saying so, rather than the command
        having to be read for the absence of a complaint."""
        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("this quest is in the student's Available tab", output)
        self.assertIn("Quest.is_available(): True", output)

    def test_quest_availability__names_the_blocking_quest_that_hides_everything_else(self):
        """One blocking quest empties the tab of every other quest the student could do, while
        leaving them all startable from the map, so the command names the quest responsible."""
        blocker = baker.make(Quest, name="Read this first", blocking=True)

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("dropped from the tab by: not crowded out by a blocking quest", output)
        self.assertIn(f'"{blocker.name}" (id {blocker.id})', output)

    def test_quest_availability__names_a_blocking_quest_the_student_has_in_progress(self):
        """A blocking quest already started empties the tab the same way, so it is named too."""
        blocker = baker.make(Quest, name="Finish this first", blocking=True)
        QuestSubmission.objects.create_submission(self.student, blocker)

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("in progress", output)
        self.assertIn(blocker.name, output)

    def test_quest_availability__reports_a_quest_the_student_hid(self):
        """Hiding a quest takes it out of the tab and leaves it startable, which reads to a
        teacher exactly like the cache being wrong."""
        self.student.profile.hidden_quests = str(self.quest.id)
        self.student.profile.save()

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("dropped from the tab by: not hidden by the student", output)
        self.assertIn("The student hid this quest themselves", output)

    def test_quest_availability__reports_a_quest_already_in_progress(self):
        """A quest in progress is out of the tab for a reason that has nothing to do with the
        cache, and the command says which."""
        QuestSubmission.objects.create_submission(self.student, self.quest)

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("dropped from the tab by: not in progress, completed or in cooldown", output)
        self.assertIn("already in progress:  True", output)

    def test_quest_availability__reports_an_unpublished_quest(self):
        """A quest nobody can see is a filter that does not depend on the student at all, and the
        advice says so rather than sending a teacher looking at that student's data."""
        self.quest.published = False
        self.quest.save()

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("is not published", output)

    def test_quest_availability__shows_each_prerequisite_and_whether_it_is_met(self):
        """The prerequisites are printed one per line with their own verdict, so an OR that is
        half met reads as met rather than as a puzzle."""
        rank = baker.make(Rank, name="Digital Novice II", xp=60)
        other_quest = baker.make(Quest, name="Intro to Digital Media Arts")
        Prereq.objects.create(parent_object=self.quest, prereq_object=rank, or_prereq_object=other_quest)

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("(rank) Digital Novice II OR (quest) Intro to Digital Media Arts", output)
        self.assertIn("live answer:   not met", output)

    def test_quest_availability__says_when_the_cached_prerequisite_answer_disagrees(self):
        """A cached answer that no longer matches a live one is the cache being stale, and the
        tab is built from the cached one, so both are printed side by side."""
        Quest.objects.get_available(self.student)
        PrereqAllConditionsMet.objects.filter(user=self.student).update(ids='[]')

        output = self.run_command("test.student", "--quest", str(self.quest.id))

        self.assertIn("live answer:   met", output)
        self.assertIn("cached answer: not met", output)
        self.assertIn("the cache is stale", output)

    def test_quest_availability__why_unlisted_is_none_for_a_quest_in_the_tab(self):
        """The helper that names the filter responsible answers None when there is none, which is
        what tells its caller the quest is listed rather than dropped."""
        command = QuestAvailabilityCommand()

        self.assertIsNone(command.why_unlisted(self.student, self.quest))

    # The whole tab #######################################################

    def test_quest_availability__with_no_quest_reports_nothing_missing(self):
        """The ordinary answer is that nothing is startable but unlisted, said in one line."""
        output = self.run_command("test.student")

        self.assertIn("Nothing is startable but missing from the tab", output)

    def test_quest_availability__with_no_quest_lists_what_is_startable_but_unlisted(self):
        """The question a teacher arrives with: which quests can this student open from the map
        and not see in their list, and why each one."""
        baker.make(Quest, name="Read this first", blocking=True)

        output = self.run_command("test.student")

        self.assertIn("Startable but MISSING from the tab", output)
        self.assertIn(self.quest.name, output)
        self.assertIn("not crowded out by a blocking quest", output)
