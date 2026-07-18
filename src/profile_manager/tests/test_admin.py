from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.db.models.signals import post_save
from django.test import RequestFactory

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from profile_manager.admin import (
    ProfileAdmin,
    create_missing_profiles,
    migrate_names_to_user_model,
)
from profile_manager.models import Profile, create_profile

User = get_user_model()


def _request_with_messages():
    """A GET request wired up with the messages framework so message_user()/messages.success() work."""
    request = RequestFactory().get('/')
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


class CreateMissingProfilesActionTest(ByteDeckTenantTestCase):
    """Tests for the create_missing_profiles admin action."""

    def test_create_missing_profiles__creates_profile_for_user_without_one(self):
        """A user that somehow has no profile gets one created by the action."""
        # Disconnect the auto-create signal so we can create a user without a profile,
        # mimicking the legacy data this action exists to repair.
        post_save.disconnect(create_profile, sender=User)
        try:
            profileless = User.objects.create_user('profileless')
        finally:
            post_save.connect(create_profile, sender=User)

        self.assertFalse(Profile.objects.filter(user=profileless).exists())

        request = _request_with_messages()
        create_missing_profiles(None, request, Profile.objects.none())

        self.assertTrue(Profile.objects.filter(user=profileless).exists())
        self.assertEqual(len(list(request._messages)), 1)

    def test_create_missing_profiles__no_message_when_nothing_to_create(self):
        """When every user already has a profile, no success message is added."""
        baker.make(User)  # profile auto-created by signal
        request = _request_with_messages()
        create_missing_profiles(None, request, Profile.objects.none())
        self.assertEqual(len(list(request._messages)), 0)


class MigrateNamesToUserModelActionTest(ByteDeckTenantTestCase):
    """Tests for the migrate_names_to_user_model admin action."""

    def test_migrate_names_to_user_model__runs_and_messages(self):
        """The action iterates the selected profiles and reports completion.

        Profile no longer stores first_name/last_name, so the hasattr guards are
        falsy and user names are left untouched -- the action simply completes.
        """
        user = baker.make(User)
        request = _request_with_messages()

        migrate_names_to_user_model(None, request, Profile.objects.filter(user=user))

        messages = list(request._messages)
        self.assertEqual(len(messages), 1)
        self.assertEqual(str(messages[0]), "Complete")


class ProfileAdminDisplayMethodsTest(ByteDeckTenantTestCase):
    """Tests for ProfileAdmin's list_display callables."""

    def setUp(self):
        self.admin = ProfileAdmin(model=Profile, admin_site=AdminSite())

    def test_get_username(self):
        user = baker.make(User, username='someone')
        self.assertEqual(self.admin.get_username(user.profile), 'someone')

    def test_get_full_name(self):
        user = baker.make(User, first_name='Ada', last_name='Lovelace')
        self.assertEqual(self.admin.get_full_name(user.profile), 'Ada Lovelace')
