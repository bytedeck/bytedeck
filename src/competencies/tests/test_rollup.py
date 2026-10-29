from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from model_bakery import baker

from competencies.models import Competency, CompetencyAssessment, ProficiencyLevel, RollupStrategy
from competencies.rollup import current_levels, describe_rollup, roll_up
from competencies.tests.test_profile_views import own_query_count
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from siteconfig.models import SiteConfig

User = get_user_model()

EMG, DEV, PRF, EXT = ProficiencyLevel.EMERGING, ProficiencyLevel.DEVELOPING, ProficiencyLevel.PROFICIENT, ProficiencyLevel.EXTENDING


def set_rollup(strategy, count=3):
    """ Set the deck's roll-up strategy, and how many latest assessments the most common level counts.

    Args:
        strategy (str): a RollupStrategy value.
        count (int): SiteConfig.competency_rollup_count.
    """
    config = SiteConfig.get()
    config.competency_rollup = strategy
    config.competency_rollup_count = count
    config.full_clean()
    config.save()


class RollUpTest(ByteDeckTenantTestCase):
    """ Tests for roll_up, which turns a student's assessments of a competency (oldest first) into
    their current level, by each strategy. """

    def test_roll_up__most_recent_is_the_latest_level(self):
        """ The most recent strategy takes the latest assessment's level, whatever came before """
        self.assertEqual(roll_up([EXT, EXT, DEV], RollupStrategy.MOST_RECENT, 3), DEV)
        self.assertEqual(roll_up([EMG], RollupStrategy.MOST_RECENT, 3), EMG)

    def test_roll_up__highest_is_the_highest_level_ever(self):
        """ The highest strategy takes the highest level assessed, however long ago """
        self.assertEqual(roll_up([EMG, EXT, DEV, EMG], RollupStrategy.HIGHEST, 3), EXT)

    def test_roll_up__most_common_counts_only_the_latest(self):
        """ The most common strategy counts only the latest ``count`` assessments, so older evidence
        drops out however much of it there is """
        levels = [EMG, EMG, EMG, PRF, DEV, PRF]

        self.assertEqual(roll_up(levels, RollupStrategy.MOST_COMMON, 3), PRF)
        self.assertEqual(roll_up(levels, RollupStrategy.MOST_COMMON, 6), EMG)

    def test_roll_up__most_common_tie_goes_to_the_most_recent_of_the_tied(self):
        """ On a tie for most common, whichever of the tied levels was assessed most recently stands,
        not the higher or the lower of them """
        self.assertEqual(roll_up([EXT, DEV, EXT, DEV], RollupStrategy.MOST_COMMON, 4), DEV)
        self.assertEqual(roll_up([DEV, EXT, DEV, EXT], RollupStrategy.MOST_COMMON, 4), EXT)
        # a three-way tie, where the latest level is one of them
        self.assertEqual(roll_up([EMG, PRF, DEV], RollupStrategy.MOST_COMMON, 3), DEV)
        # the latest level isn't in the tie: the most recent of the tied levels stands
        self.assertEqual(roll_up([PRF, EXT, PRF, EXT, EMG], RollupStrategy.MOST_COMMON, 5), EXT)

    def test_roll_up__most_common_with_fewer_assessments_than_counted(self):
        """ With fewer assessments than the count, all of them count """
        self.assertEqual(roll_up([PRF, PRF, DEV], RollupStrategy.MOST_COMMON, 5), PRF)
        self.assertEqual(roll_up([DEV], RollupStrategy.MOST_COMMON, 5), DEV)


class DescribeRollupTest(ByteDeckTenantTestCase):
    """ Tests for describe_rollup, the explanation of what a current level is under each strategy. """

    def test_describe_rollup__each_strategy(self):
        """ Each strategy is described in words, the most common one with the deck's count and its tie rule """
        config = SiteConfig.get()
        self.assertEqual(describe_rollup(config), "the level of its most recent assessment")

        config.competency_rollup = RollupStrategy.HIGHEST
        self.assertEqual(describe_rollup(config), "the highest level it has been assessed at")

        config.competency_rollup = RollupStrategy.MOST_COMMON
        config.competency_rollup_count = 4
        self.assertEqual(
            describe_rollup(config),
            "the level it was assessed at most often in its latest 4 assessments (on a tie, whichever of those levels came most recently)",
        )


class RollupSettingsTest(ByteDeckTenantTestCase):
    """ Tests for the deck's roll-up settings on SiteConfig. """

    def test_rollup_settings__most_recent_of_the_latest_three_by_default(self):
        """ A deck starts on the most recent assessment (BC's guidance), with 3 latest assessments
        counted should it switch to the most common level """
        config = SiteConfig.get()

        self.assertEqual((config.competency_rollup, config.competency_rollup_count), (RollupStrategy.MOST_RECENT, 3))

    def test_rollup_settings__the_most_common_level_counts_at_least_two(self):
        """ Counting only the latest assessment would just be the most recent one, so at least two count """
        config = SiteConfig.get()
        config.competency_rollup_count = 1

        with self.assertRaises(ValidationError) as raised:
            config.full_clean()
        self.assertIn('competency_rollup_count', raised.exception.message_dict)


class CurrentLevelsTest(ByteDeckTenantTestCase):
    """ Tests for current_levels, the roll-up of students' evidence into their current level per
    competency that every page showing a current level reads. """

    def setUp(self):
        """ Creates two students and two competencies to assess them on. """
        self.student = baker.make(User)
        self.other_student = baker.make(User)
        self.thinking = baker.make(Competency, name="Critical Thinking")
        self.communicating = baker.make(Competency, name="Communicating")

    def assess(self, competency, level, minutes_ago, user=None):
        """ Records an assessment stamped the given number of minutes ago (auto_now_add stamps it
        now, so the stamp is set afterwards).

        Returns:
            CompetencyAssessment: the saved assessment.
        """
        assessment = CompetencyAssessment.objects.create(user=user or self.student, competency=competency, level=level)
        CompetencyAssessment.objects.filter(pk=assessment.pk).update(timestamp=timezone.now() - timedelta(minutes=minutes_ago))
        return assessment

    def test_current_levels__the_default_is_the_most_recent(self):
        """ By default each competency's current level is its most recent assessment's, whatever order
        they were recorded in """
        self.assess(self.thinking, DEV, minutes_ago=5)
        self.assess(self.thinking, EXT, minutes_ago=30)
        self.assess(self.communicating, EMG, minutes_ago=20)
        self.assess(self.communicating, PRF, minutes_ago=10)

        self.assertEqual(current_levels(user=self.student)[self.student.pk], {self.thinking.pk: DEV, self.communicating.pk: PRF})

    def test_current_levels__timestamp_ties_go_to_the_one_recorded_last(self):
        """ Two assessments stamped the same moment are taken in the order they were recorded """
        earlier = self.assess(self.thinking, DEV, minutes_ago=5)
        later = self.assess(self.thinking, PRF, minutes_ago=5)
        # each assess() reads the clock separately, so give the two the very same stamp
        CompetencyAssessment.objects.filter(pk__in=[earlier.pk, later.pk]).update(timestamp=timezone.now() - timedelta(minutes=5))

        self.assertEqual(current_levels(user=self.student)[self.student.pk], {self.thinking.pk: PRF})

    def test_current_levels__by_the_decks_strategy(self):
        """ Switching the deck's strategy changes the current levels it gives """
        for minutes_ago, level in ((40, EXT), (30, DEV), (20, PRF), (10, DEV)):
            self.assess(self.thinking, level, minutes_ago)

        set_rollup(RollupStrategy.HIGHEST)
        self.assertEqual(current_levels(user=self.student)[self.student.pk], {self.thinking.pk: EXT})

        set_rollup(RollupStrategy.MOST_COMMON, count=3)
        self.assertEqual(current_levels(user=self.student)[self.student.pk], {self.thinking.pk: DEV})

        set_rollup(RollupStrategy.MOST_RECENT)
        self.assertEqual(current_levels(user=self.student)[self.student.pk], {self.thinking.pk: DEV})

    def test_current_levels__each_student_separately_and_filtered(self):
        """ Over several students each gets their own levels, the filters choose the students and
        competencies, and a student with no evidence has none """
        self.assess(self.thinking, DEV, minutes_ago=10)
        self.assess(self.thinking, EXT, minutes_ago=5, user=self.other_student)
        self.assess(self.communicating, EMG, minutes_ago=5, user=self.other_student)
        nobody = baker.make(User)

        levels = current_levels(user_id__in=[self.student.pk, self.other_student.pk, nobody.pk], competency=self.thinking)

        self.assertEqual(levels[self.student.pk], {self.thinking.pk: DEV})
        self.assertEqual(levels[self.other_student.pk], {self.thinking.pk: EXT})
        self.assertEqual(levels[nobody.pk], {})

    def test_current_levels__one_query(self):
        """ A whole class's levels take one query, however many students and competencies there are """
        students = baker.make(User, _quantity=3)
        for student in students:
            for competency in baker.make(Competency, _quantity=3):
                self.assess(competency, PRF, minutes_ago=2, user=student)
                self.assess(competency, DEV, minutes_ago=1, user=student)
        SiteConfig.get()  # the deck's settings are cached between requests

        with CaptureQueriesContext(connection) as queries:
            levels = current_levels(user_id__in=[student.pk for student in students])

        self.assertEqual(own_query_count(queries), 1)
        self.assertEqual(sum(len(student_levels) for student_levels in levels.values()), 9)
