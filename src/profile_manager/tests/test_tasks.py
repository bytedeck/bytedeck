from django.contrib.auth import get_user_model

from django_tenants.test.cases import TenantTestCase

from profile_manager.tasks import invalidate_profile_xp_cache_in_all_schemas
from profile_manager.models import Profile

from siteconfig.models import SiteConfig
from courses.models import CourseStudent, Course
from model_bakery import baker


from django.test.utils import override_settings

User = get_user_model()


class ProfleTasksTests(TenantTestCase):
    """
    Run tasks (from tenant module) asyncronously with apply()
    """

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_recalculate_current_xp_profile_on_all_schemas(self):
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
