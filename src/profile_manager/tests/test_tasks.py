from unittest import mock

from django.contrib.auth import get_user_model
from django.db import DataError

from hackerspace_online.tests.utils import ByteDeckTenantTestCase

from profile_manager.tasks import invalidate_profile_xp_cache_in_all_schemas, invalidate_profile_xp_cache_on_schema
from profile_manager.models import Profile

from siteconfig.models import SiteConfig
from courses.models import CourseStudent, Course
from model_bakery import baker


from django.test.utils import override_settings

User = get_user_model()


class ProfleTasksTests(ByteDeckTenantTestCase):
    """
    Run tasks (from tenant module) asyncronously with apply()
    """

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_invalidate_profile_xp_cache_in_all_schemas__resets_cached_values(self):
        """Running the task resets each active-semester profile's cached xp and mark to 0."""
        self.course = baker.make(Course)
        self.active_semester = SiteConfig().get().active_semester

        names = [f"user-{index}" for index in range(8)][::-1]

        active_semester_students = baker.make(User, username=names.pop, _quantity=2)

        for user in active_semester_students:
            baker.make(
                CourseStudent,
                user=user,
                course=self.course,
                semester=self.active_semester,
            )

            # Set the current xp to an arbitrary value just to make sure it gets reset
            user.profile.xp_cached = 100
            user.profile.mark_cached = 100
            user.profile.save()

            self.assertEqual(user.profile.xp_cached, 100)
            self.assertEqual(user.profile.mark_cached, 100)

        # Run the task for recalculating the current xp
        invalidate_profile_xp_cache_in_all_schemas.apply()

        for profile in Profile.objects.all_for_active_semester():
            self.assertEqual(profile.xp_cached, 0)
            self.assertEqual(profile.mark_cached, 0)


class InvalidateXpCacheResilienceTest(ByteDeckTenantTestCase):
    """Regression for #2035: one profile that raises while invalidating its cache
    (e.g. the mark_cached overflow) must not abort the whole schema's refresh --
    the task logs it and carries on so later profiles aren't left stale."""

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_invalidate_profile_xp_cache_on_schema__skips_failing_profile_and_continues(self):
        """A profile raising in xp_invalidate_cache is skipped and reported; the
        remaining active-semester profiles are still invalidated."""
        course = baker.make(Course)
        active_semester = SiteConfig.get().active_semester
        students = baker.make(User, _quantity=3)
        for user in students:
            baker.make(CourseStudent, user=user, course=course, semester=active_semester)
            # Bogus cached value a real invalidation would reset to 0.
            user.profile.xp_cached = 999
            user.profile.save()

        target_pk = students[0].profile.pk
        real_invalidate = Profile.xp_invalidate_cache

        def flaky(profile_self):
            """Raise for the one target profile, behave normally for the rest."""
            if profile_self.pk == target_pk:
                raise DataError("numeric field overflow")
            return real_invalidate(profile_self)

        with mock.patch.object(Profile, "xp_invalidate_cache", autospec=True, side_effect=flaky):
            result = invalidate_profile_xp_cache_on_schema.apply()

        # The task completed instead of crashing, and reported the single failure.
        self.assertTrue(result.successful())
        self.assertIn("1 failed", result.result)

        # The loop continued past the failure regardless of iteration order: every
        # non-target profile was invalidated (999 -> 0), the target left untouched.
        for user in students:
            profile = Profile.objects.get(pk=user.profile.pk)
            if profile.pk == target_pk:
                self.assertEqual(profile.xp_cached, 999)
            else:
                self.assertEqual(profile.xp_cached, 0)
