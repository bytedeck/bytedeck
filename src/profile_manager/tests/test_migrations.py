"""Tests for profile_manager's data migrations."""
from datetime import timedelta
from importlib import import_module

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.utils import timezone

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from profile_manager.models import Profile

User = get_user_model()
last_active_migration = import_module("profile_manager.migrations.0022_profile_last_active")


class StartFromLastLoginMigrationTest(ByteDeckTenantTestCase):
    """The data migration that starts each profile's last activity at the last sign-in (#2849)."""

    def test_start_from_last_login__copies_the_last_sign_in(self):
        """A profile with no activity yet starts at its person's last sign-in."""
        signed_in = timezone.now() - timedelta(days=20)
        student = User.objects.create_user('migrated_student', last_login=signed_in)
        Profile.objects.filter(user=student).update(last_active=None)

        last_active_migration.start_from_last_login(django_apps, None)

        self.assertEqual(Profile.objects.get(user=student).last_active, signed_in)

    def test_start_from_last_login__keeps_a_recorded_time_and_a_blank_for_no_sign_in(self):
        """A time already recorded is kept, and a person who never signed in stays blank."""
        recorded = timezone.now() - timedelta(hours=2)
        active = User.objects.create_user('active_student', last_login=timezone.now() - timedelta(days=20))
        Profile.objects.filter(user=active).update(last_active=recorded)
        never = User.objects.create_user('never_signed_in')

        last_active_migration.start_from_last_login(django_apps, None)

        self.assertEqual(Profile.objects.get(user=active).last_active, recorded)
        self.assertIsNone(Profile.objects.get(user=never).last_active)
