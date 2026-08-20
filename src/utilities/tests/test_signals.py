"""The fixture-loading guard on the project's save receivers (issue #2548)."""
from importlib import import_module
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.test import SimpleTestCase

from model_bakery import baker

from courses.models import CourseStudent
from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from profile_manager.models import Profile
from utilities.signals import disable_for_loaddata

User = get_user_model()


#: Save receivers that read or write rows other than the one being saved, or queue work
#: that will, so each must sit out a raw (fixture) save. Kept as data rather than prose so
#: that the audit below fails when a new receiver of that kind arrives unguarded.
RECEIVERS_THAT_SIT_OUT_FIXTURE_LOADING = [
    ('announcements.signals', 'save_announcement_signal'),
    ('badges.models', 'post_save_receiver'),
    ('courses.models', 'coursestudent_post_save_callback'),
    ('courses.models', 'coursestudent_adopt_unstamped_work_callback'),
    ('courses.models', 'semester_adopt_unstamped_work_callback'),
    ('djcytoscape.signals', 'badge_regenerate_related_maps'),
    ('djcytoscape.signals', 'prereq_regenerate_related_maps'),
    ('prerequisites.signals', 'on_quest_badge_save_with_rank_prereq'),
    ('prerequisites.signals', 'update_cache_triggered_by_prereq'),
    ('prerequisites.signals', 'update_cache_triggered_by_quest_without_prereqs'),
    ('prerequisites.signals', 'update_cache_triggered_by_quests_available_outside_course'),
    ('prerequisites.signals', 'update_cache_triggered_by_task_completion'),
    ('prerequisites.signals', 'update_conditions_met'),
    ('profile_manager.models', 'create_profile'),
]

#: Save receivers deliberately left to run during a fixture load, with the reason. The
#: cache ones because a load is precisely when a cached list is stale and must go; the
#: last because it only tidies the instance on its way to the database and touches nothing
#: else, which is what pre_save is for.
RECEIVERS_THAT_RUN_DURING_FIXTURE_LOADING = [
    ('badges.models', 'badge_rarity_invalidate_cache_callback'),
    ('courses.models', 'rank_invalidate_cache_callback'),
    ('siteconfig.models', 'invalidate_siteconfig_cache_signal'),
    ('quest_manager.signals', 'quest_pre_save_callback'),
]


class DisableForLoaddataTest(SimpleTestCase):
    """The decorator itself."""

    def setUp(self):
        """Wrap a plain mock, so the assertions are about the decorator and nothing else."""
        self.handler = Mock(return_value='ran')
        self.wrapped = disable_for_loaddata(self.handler)

    def test_disable_for_loaddata__skips_a_raw_save(self):
        """raw=True is Django deserializing a fixture, which is the whole point of this."""
        self.assertIsNone(self.wrapped(instance='thing', raw=True))
        self.handler.assert_not_called()

    def test_disable_for_loaddata__runs_an_ordinary_save(self):
        """Every save the app itself makes carries raw=False, and must be unaffected."""
        self.assertEqual(self.wrapped(instance='thing', raw=False), 'ran')
        self.handler.assert_called_once_with(instance='thing', raw=False)

    def test_disable_for_loaddata__runs_when_the_signal_sends_no_raw_at_all(self):
        """post_delete and pre_delete carry no raw kwarg, and several of the receivers this
        wraps are connected to a delete signal as well as a save one. Those halves have
        nothing to sit out, so a missing raw must read as "go ahead" rather than as true."""
        self.assertEqual(self.wrapped(instance='thing'), 'ran')
        self.handler.assert_called_once_with(instance='thing')

    def test_disable_for_loaddata__keeps_the_wrapped_receivers_identity(self):
        """Django reports receivers by module and name and the tracebacks here are read by
        people, so the wrapper has to keep the name and docstring it was given rather than
        presenting every guarded receiver as "wrapper"."""
        def quest_saved(**kwargs):
            """What the real receivers look like."""

        wrapped = disable_for_loaddata(quest_saved)

        self.assertEqual(wrapped.__name__, 'quest_saved')
        self.assertEqual(wrapped.__doc__, 'What the real receivers look like.')
        self.assertTrue(wrapped.disabled_for_loaddata)


class SaveReceiverFixtureAuditTest(SimpleTestCase):
    """Which receivers sit out a fixture load, checked rather than described.

    Applying the guard to some receivers and not others is how the half-guarded state this
    fixes came about, so both halves of the decision are asserted here.
    """

    def test_receivers_that_touch_other_rows__all_sit_out_fixture_loading(self):
        """Every receiver that reads or writes beyond its own instance is wrapped."""
        unguarded = [
            f'{module}.{name}'
            for module, name in RECEIVERS_THAT_SIT_OUT_FIXTURE_LOADING
            if not getattr(getattr(import_module(module), name), 'disabled_for_loaddata', False)
        ]
        self.assertEqual(unguarded, [], f'not wrapped in @disable_for_loaddata: {unguarded}')

    def test_cache_and_instance_only_receivers__still_run_during_fixture_loading(self):
        """The exceptions are deliberate, so wrapping one of them should fail this too. A
        load is exactly when a cached list of ranks or rarities is stale, and tidying the
        instance on its way to the database touches nothing a part-loaded database breaks."""
        guarded = [
            f'{module}.{name}'
            for module, name in RECEIVERS_THAT_RUN_DURING_FIXTURE_LOADING
            if getattr(getattr(import_module(module), name), 'disabled_for_loaddata', False)
        ]
        self.assertEqual(guarded, [], f'unexpectedly wrapped in @disable_for_loaddata: {guarded}')


class SaveReceiverRawBehaviourTest(ByteDeckTenantTestCase):
    """What the guard actually prevents, for two of the receivers it wraps."""

    def test_create_profile__a_fixture_load_makes_no_profile(self):
        """A fixture carrying users carries their profiles too, so building one here would
        collide with the row still to be loaded, or leave a second one behind."""
        user = User(username='arriving.in.a.fixture')
        user.save()
        Profile.objects.filter(user=user).delete()

        post_save.send(sender=User, instance=user, created=True, raw=True)

        self.assertFalse(Profile.objects.filter(user=user).exists())

    def test_coursestudent_post_save__a_fixture_load_leaves_the_cached_xp_alone(self):
        """This one recomputes a student's XP and mark by aggregating three tables. Part way
        through a load those tables are incomplete, so the figure it would store is wrong,
        and it would be stored rather than merely reported."""
        student = baker.make(User)
        registration = baker.make(CourseStudent, user=student)
        student.profile.refresh_from_db()
        student.profile.xp_cached = 999
        student.profile.save()

        post_save.send(sender=CourseStudent, instance=registration, created=False, raw=True)

        student.profile.refresh_from_db()
        self.assertEqual(student.profile.xp_cached, 999)
