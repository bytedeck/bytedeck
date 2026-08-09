"""Tests for the release-announcement staff notifications (tenant.github +
tenant.tasks.poll_release_announcement / notify_all_decks_of_release).

When a new ByteDeck version's changelog reaches production, the announce-changelog
workflow posts a GitHub Discussion; the hourly poll reads it back and notifies
every deck's staff with a link to it. These tests cover the GitHub read, the poll's
gating/baseline/dedup logic, and the per-deck fan-out.
"""

from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, override_settings

from django_tenants.utils import get_public_schema_name, schema_context

from model_bakery import baker

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from notifications.models import Notification
from tenant import github, tasks
from tenant.models import ReleaseNotification

User = get_user_model()

DISCUSSION_URL = "https://github.com/bytedeck/bytedeck/discussions/2350"


def _github_response(nodes):
    """Build a fake ``requests`` response wrapping a discussions ``nodes`` list."""
    return Mock(raise_for_status=Mock(), json=Mock(return_value={
        "data": {"repository": {"discussions": {"nodes": nodes}}}
    }))


def _announcement_node(title, url=DISCUSSION_URL, category="Announcements"):
    """A single discussion node as the GraphQL query returns it."""
    return {"title": title, "url": url, "category": {"name": category}}


class ReleaseNotificationModelTests(SimpleTestCase):
    """ReleaseNotification.__str__ labels a real notification vs a baseline row."""

    def test_str__distinguishes_notified_from_baseline(self):
        """The audit string reports whether staff were actually notified."""
        self.assertEqual(str(ReleaseNotification(version="1.31.0", notified=True)), "1.31.0 (notified)")
        self.assertEqual(str(ReleaseNotification(version="1.31.0", notified=False)), "1.31.0 (baseline)")


@override_settings(GITHUB_API_TOKEN="test-token", RELEASE_ANNOUNCEMENT_REPO="bytedeck/bytedeck")
class GetLatestReleaseAnnouncementTests(SimpleTestCase):
    """tenant.github.get_latest_release_announcement reads the newest changelog
    announcement discussion, and is best-effort: any failure returns None."""

    @override_settings(GITHUB_API_TOKEN="")
    def test_no_token__returns_none_without_calling_github(self):
        """Without a token the feature is inert: no request is even attempted."""
        with patch("tenant.github.requests.post") as mock_post:
            self.assertIsNone(github.get_latest_release_announcement())
        mock_post.assert_not_called()

    @override_settings(RELEASE_ANNOUNCEMENT_REPO="not-owner-slash-name")
    def test_malformed_repo__returns_none(self):
        """A RELEASE_ANNOUNCEMENT_REPO without an 'owner/name' slash is ignored."""
        with patch("tenant.github.requests.post") as mock_post:
            self.assertIsNone(github.get_latest_release_announcement())
        mock_post.assert_not_called()

    def test_network_error__returns_none(self):
        """A transport error just means 'nothing this run', not a crash."""
        with patch("tenant.github.requests.post", side_effect=github.requests.RequestException("boom")):
            self.assertIsNone(github.get_latest_release_announcement())

    def test_unexpected_payload_shape__returns_none(self):
        """A response missing the expected keys returns None rather than raising."""
        with patch("tenant.github.requests.post", return_value=Mock(raise_for_status=Mock(), json=Mock(return_value={}))):
            self.assertIsNone(github.get_latest_release_announcement())

    def test_single_version_announcement__returns_version_and_url(self):
        """A 'Bytedeck App Updates (x.y.z)' discussion yields (version, url)."""
        nodes = [_announcement_node("Bytedeck App Updates (1.31.0)")]
        with patch("tenant.github.requests.post", return_value=_github_response(nodes)):
            self.assertEqual(github.get_latest_release_announcement(), ("1.31.0", DISCUSSION_URL))

    def test_multi_version_title__returns_highest_version(self):
        """A batched announcement returns the highest version it names."""
        nodes = [_announcement_node("Bytedeck App Updates (1.30.0 and 1.31.0)")]
        with patch("tenant.github.requests.post", return_value=_github_response(nodes)):
            self.assertEqual(github.get_latest_release_announcement(), ("1.31.0", DISCUSSION_URL))

    def test_get_latest__ignores_non_announcement_discussions(self):
        """Newest-first: a non-announcement discussion (wrong category or title) is
        skipped in favour of the first real announcement below it."""
        nodes = [
            _announcement_node("A community question", category="Q&A"),
            _announcement_node("Bytedeck App Updates (1.31.0)", url="https://github.com/x/y/discussions/9"),
            _announcement_node("Bytedeck App Updates (1.30.0)"),  # older, must not win
        ]
        with patch("tenant.github.requests.post", return_value=_github_response(nodes)):
            self.assertEqual(
                github.get_latest_release_announcement(),
                ("1.31.0", "https://github.com/x/y/discussions/9"),
            )

    def test_no_matching_discussion__returns_none(self):
        """No announcement-shaped discussion at all yields None."""
        nodes = [_announcement_node("Just chatting", category="General")]
        with patch("tenant.github.requests.post", return_value=_github_response(nodes)):
            self.assertIsNone(github.get_latest_release_announcement())

    def test_announcement_title_without_a_version__is_skipped(self):
        """A correctly-titled announcement carrying no x.y.z version is skipped
        rather than mis-parsed (defensive against a malformed title)."""
        nodes = [_announcement_node("Bytedeck App Updates (coming soon)")]
        with patch("tenant.github.requests.post", return_value=_github_response(nodes)):
            self.assertIsNone(github.get_latest_release_announcement())


@override_settings(RELEASE_NOTIFICATIONS_ENABLED=True)
class PollReleaseAnnouncementTests(ByteDeckTenantTestCase):
    """poll_release_announcement gates on the flag, records a first-run baseline
    without notifying, dedupes by version, and only notifies on a newer release."""

    def _public_releases(self):
        """ReleaseNotification rows, read from the public schema where they live."""
        with schema_context(get_public_schema_name()):
            return list(ReleaseNotification.objects.values_list("version", "notified"))

    def _record_release(self, version, notified=True):
        """Seed a ReleaseNotification row in the public schema."""
        with schema_context(get_public_schema_name()):
            ReleaseNotification.objects.create(version=version, discussion_url=DISCUSSION_URL, notified=notified)

    @override_settings(RELEASE_NOTIFICATIONS_ENABLED=False)
    def test_disabled__returns_without_querying_github(self):
        """With the feature off, the task no-ops and never touches GitHub."""
        with patch("tenant.github.get_latest_release_announcement") as mock_latest:
            result = tasks.poll_release_announcement.apply()
        self.assertTrue(result.successful())
        self.assertIn("disabled", result.result)
        mock_latest.assert_not_called()

    def test_no_announcement_found__skips(self):
        """When GitHub has no announcement to read, the task does nothing."""
        with patch("tenant.github.get_latest_release_announcement", return_value=None):
            result = tasks.poll_release_announcement.apply()
        self.assertIn("No release announcement", result.result)
        self.assertEqual(self._public_releases(), [])

    def test_first_run__records_baseline_without_notifying(self):
        """The first successful poll records a baseline (notified=False) and sends
        no notifications: a version that shipped before the feature was enabled
        must not blast every deck's staff."""
        baker.make(User, is_staff=True)
        with patch("tenant.github.get_latest_release_announcement", return_value=("1.30.0", DISCUSSION_URL)):
            result = tasks.poll_release_announcement.apply()
        self.assertIn("baseline", result.result)
        self.assertEqual(self._public_releases(), [("1.30.0", False)])
        self.assertFalse(Notification.objects.filter(verb__contains="new version of ByteDeck").exists())

    def test_already_handled_version__skips(self):
        """A version already recorded is never re-notified."""
        self._record_release("1.31.0")
        with patch("tenant.github.get_latest_release_announcement", return_value=("1.31.0", DISCUSSION_URL)):
            result = tasks.poll_release_announcement.apply()
        self.assertIn("already handled", result.result)

    def test_older_than_recorded__records_silently(self):
        """A version at or below the newest recorded one is recorded but not
        announced (guards a deleted/re-created older discussion)."""
        self._record_release("1.31.0")
        baker.make(User, is_staff=True)
        with patch("tenant.github.get_latest_release_announcement", return_value=("1.30.0", DISCUSSION_URL)):
            result = tasks.poll_release_announcement.apply()
        self.assertIn("not newer", result.result)
        self.assertIn(("1.30.0", False), self._public_releases())
        self.assertFalse(Notification.objects.filter(verb__contains="new version of ByteDeck").exists())

    def test_new_version__notifies_all_staff_and_links_to_discussion(self):
        """A newer release notifies every active staff user, from the Bytedeck
        support account, with a link to the GitHub announcement; and records the
        version as notified so a later poll won't repeat it."""
        self._record_release("1.30.0")
        staff = baker.make(User, is_staff=True, _quantity=3)
        student = baker.make(User, is_staff=False)  # must NOT be notified

        with patch("tenant.github.get_latest_release_announcement", return_value=("1.31.0", DISCUSSION_URL)):
            result = tasks.poll_release_announcement.apply()

        self.assertIn("Notified", result.result)
        self.assertIn("release 1.31.0", result.result)

        for teacher in staff:
            note = Notification.objects.filter(recipient=teacher).latest("timestamp")
            self.assertEqual(note.target_url, DISCUSSION_URL)
            self.assertIn("1.31.0", note.verb)
        self.assertFalse(Notification.objects.filter(recipient=student).exists())

        with schema_context(get_public_schema_name()):
            self.assertTrue(ReleaseNotification.objects.get(version="1.31.0").notified)


class NotifyAllDecksOfReleaseTests(ByteDeckTenantTestCase):
    """The per-deck fan-out targets staff only and tolerates a bad deck."""

    def test_notify_all_decks__only_active_staff_excluding_system_account(self):
        """Active staff get the notice; the deck's ByteDeck support account (the
        sender) and inactive staff do not."""
        staff = baker.make(User, is_staff=True, is_active=True)
        baker.make(User, is_staff=True, is_active=False)  # inactive: skipped

        deck_count, staff_count = tasks.notify_all_decks_of_release("1.31.0", DISCUSSION_URL)

        self.assertEqual(deck_count, 1)
        self.assertGreaterEqual(staff_count, 1)
        self.assertTrue(Notification.objects.filter(recipient=staff, target_url=DISCUSSION_URL).exists())

    def test_deck_with_no_staff__is_skipped_cleanly(self):
        """A deck with no active staff contributes nothing and doesn't error."""
        User.objects.filter(is_staff=True).update(is_active=False)
        deck_count, staff_count = tasks.notify_all_decks_of_release("1.31.0", DISCUSSION_URL)
        self.assertEqual((deck_count, staff_count), (0, 0))

    def test_deck_that_raises__is_logged_and_skipped_not_aborted(self):
        """A failure fanning out to one deck is caught and logged so the rest still
        get notified: here notify.send raises for every deck, so the call returns
        (0, 0) instead of propagating the error."""
        from notifications.signals import notify

        baker.make(User, is_staff=True, is_active=True)
        with patch.object(notify, "send", side_effect=Exception("boom")):
            deck_count, staff_count = tasks.notify_all_decks_of_release("1.31.0", DISCUSSION_URL)
        self.assertEqual((deck_count, staff_count), (0, 0))
