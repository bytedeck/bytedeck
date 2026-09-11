from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from django.contrib.contenttypes.models import ContentType
from unittest import TestCase
from model_bakery import baker
from model_bakery.recipe import Recipe

from hackerspace_online.tests.utils import ByteDeckTenantTestCase
from notifications.models import Notification, new_notification

User = get_user_model()


class NotificationModelTest(ByteDeckTenantTestCase):

    @classmethod
    def setUpTestData(cls):
        """Create a teacher and a student (a teacher must exist first or student creation fails)."""
        User = get_user_model()
        cls.teacher = Recipe(User, is_staff=True).make()  # need a teacher or student creation will fail.
        cls.student = baker.make(User)

    def test_notification_creation__creates_and_saves(self):
        """A Notification can be created, cleaned, saved, and rendered to a string."""
        notification = Notification.objects.create(
            recipient=self.student,
            sender_content_type=ContentType.objects.get_for_model(self.teacher),
            sender_object_id=self.teacher.id,
            verb="sent you a notification"
        )
        notification.full_clean()
        notification.save()
        self.assertIsInstance(notification, Notification)
        self.assertIsNotNone(str(notification))

    def test_mark_read__marks_notification_read(self):
        """mark_read() flips an unread notification to read."""
        notification = baker.make(
            Notification,
            sender_content_type=ContentType.objects.get_for_model(self.teacher), sender_object_id=self.teacher.id,
        )
        self.assertTrue(notification.unread)
        notification.mark_read()
        self.assertFalse(notification.unread)

    def test_recent__returns_at_most_five_unread(self):
        """recent() returns only the five most recent unread notifications."""
        Notification.objects.all().delete()  # clear any created as a side effect of user setup
        for _ in range(6):
            Notification.objects.create(
                recipient=self.student,
                sender_content_type=ContentType.objects.get_for_model(self.teacher),
                sender_object_id=self.teacher.id,
                verb="pinged you",
                unread=True,
            )
        recent = Notification.objects.all().recent()
        self.assertEqual(len(recent), 5)
        self.assertTrue(all(note.unread for note in recent))

    def _latest_notification(self):
        """Return the most recently created Notification (new_notification returns nothing)."""
        return Notification.objects.order_by('id').last()

    def test_get_link__with_target_and_action_renders_both(self):
        """get_link() emphasises the target and quotes the action when the notification has both."""
        target = baker.make('announcements.Announcement')
        action = baker.make('comments.Comment')
        new_notification(
            self.teacher,
            recipient=self.student,
            affected_users=[self.student],
            target=target,
            action=action,
            verb="commented on",
        )
        link = self._latest_notification().get_link()
        self.assertIn(f"<em>{target}</em>", link)
        self.assertIn('with "', link)

    def test_get_link__with_target_no_action_renders_target_only(self):
        """get_link() emphasises the target but omits the 'with ...' clause when there is no action object."""
        target = baker.make('announcements.Announcement')
        new_notification(
            self.teacher,
            recipient=self.student,
            affected_users=[self.student],
            target=target,
            verb="posted",
        )
        link = self._latest_notification().get_link()
        self.assertIn(f"<em>{target}</em>", link)
        self.assertNotIn('with "', link)

    def test_get_link__without_target_has_no_emphasis(self):
        """get_link() renders only the sender/verb (no <em> target) when there is no target object."""
        new_notification(
            self.teacher,
            recipient=self.student,
            affected_users=[self.student],
            verb="sent you a notification",
        )
        link = self._latest_notification().get_link()
        self.assertNotIn("<em>", link)
        self.assertTrue(link.endswith("</a>"))

    def test_new_notification__explicit_url_becomes_the_destination(self):
        """A notification created with url= stores it and links there (through the
        read-tracking redirect) from both the dropdown and the list page."""
        new_notification(
            self.teacher,
            recipient=self.student,
            affected_users=[self.student],
            verb="sent a reminder about this deck.",
            url='/decks/subscription/',
        )
        note = self._latest_notification()
        self.assertEqual(note.target_url, '/decks/subscription/')
        self.assertTrue(note.get_url().endswith('?next=/decks/subscription/'))
        self.assertIn("?next=/decks/subscription/", note.get_link())

    def test_str__url_only_notification_links_the_verb_text(self):
        """With an explicit url and no target object, the list page renders the verb
        itself as the link text: the anchor would otherwise be empty, leaving the
        destination unreachable from the notifications list."""
        new_notification(
            self.teacher,
            recipient=self.student,
            affected_users=[self.student],
            verb="sent a reminder about this deck.",
            url='/decks/subscription/',
        )
        text = str(self._latest_notification())
        self.assertIn("?next=/decks/subscription/'>sent a reminder about this deck.</a>", text)

    def test_str__link_text_keeps_the_verb_plain_with_one_small_link(self):
        """With url= and link_text=, the list page renders the verb as plain text
        followed by one small link (maintainer request, 2026-08-08), and the
        dropdown's single-anchor row completes the sentence with the link text."""
        new_notification(
            self.teacher,
            recipient=self.student,
            affected_users=[self.student],
            verb="sent a reminder. See your",
            url='/decks/subscription/',
            link_text='subscription details page.',
        )
        note = self._latest_notification()
        self.assertEqual(note.target_link_text, 'subscription details page.')
        text = str(note)
        # the verb sits OUTSIDE the anchor; only the link text is inside it
        self.assertIn("sent a reminder. See your <a href=", text)
        self.assertIn("?next=/decks/subscription/'>subscription details page.</a>", text)
        self.assertIn(" See your subscription details page.</a>", note.get_link())

    def test_get_url__explicit_url_overrides_the_targets_own_page(self):
        """When both a target object and an explicit url are given, the explicit url
        wins as the destination while the target still provides the link text."""
        target = baker.make('announcements.Announcement')
        new_notification(
            self.teacher,
            recipient=self.student,
            affected_users=[self.student],
            target=target,
            verb="posted",
            url='/decks/subscription/',
        )
        note = self._latest_notification()
        self.assertTrue(note.get_url().endswith('?next=/decks/subscription/'))
        self.assertIn(f"<em>{target}</em>", str(note))

    def test_new_notification__creates_unread_for_recipient(self):
        """new_notification() creates a single unread notification for the recipient."""
        # make sure the student doesn't have any notifications yet
        notes_before = self.student.notifications.all()
        self.assertEqual(notes_before.count(), 0)

        kwargs = {
            'recipient': self.student,
            'verb': 'tested'
        }
        new_notification(self.teacher, **kwargs)

        # now the student should have one if it worked.
        notes_after = self.student.notifications.all()
        self.assertEqual(notes_after.count(), 1)

        notes_unread = Notification.objects.all_unread(self.student)
        self.assertEqual(notes_unread.count(), 1)

    def test_new_notification__bulk_creates_one_insert_for_many_recipients(self):
        """new_notification writes every recipient's notification in a single bulk
        INSERT instead of one save() per recipient."""
        recipients = baker.make(User, _quantity=5)

        with CaptureQueriesContext(connection) as ctx:
            new_notification(
                self.teacher,
                recipient=self.student,  # required kwarg, unused when affected_users given
                affected_users=recipients,
                verb="tested",
            )

        # a single bulk INSERT covers all recipients (was one INSERT per recipient)
        inserts = [q for q in ctx.captured_queries if 'insert into "notifications_notification"' in q['sql'].lower()]
        self.assertEqual(len(inserts), 1)
        self.assertEqual(Notification.objects.filter(recipient__in=recipients).count(), 5)

    def test_new_notification__skips_sender(self):
        """A user does not get notified about their own action, even when listed
        in affected_users (regression guard for the bulk_create refactor)."""
        # clear notifications created as a side effect of user creation in setUp
        Notification.objects.all().delete()

        new_notification(
            self.teacher,
            recipient=self.student,
            affected_users=[self.teacher, self.student],
            verb="tested",
        )
        # only the student (not the sender/teacher) should have a notification
        self.assertEqual(Notification.objects.filter(recipient=self.teacher).count(), 0)
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), 1)

    def test_mark_all_read__single_update_sets_unread_and_time_read(self):
        """mark_all_read marks every unread notification read and stamps time_read
        in one UPDATE (the previous two-update version left time_read unset)."""
        baker.make(
            Notification, recipient=self.student, unread=True, time_read=None, _quantity=3,
            sender_content_type=ContentType.objects.get_for_model(self.teacher), sender_object_id=self.teacher.id,
        )
        self.assertEqual(Notification.objects.all_unread(self.student).count(), 3)

        with CaptureQueriesContext(connection) as ctx:
            Notification.objects.all().mark_all_read(self.student)

        updates = [q for q in ctx.captured_queries if q['sql'].lstrip().upper().startswith('UPDATE')]
        self.assertEqual(len(updates), 1)

        self.assertEqual(Notification.objects.all_unread(self.student).count(), 0)
        # time_read must actually be set now, not left None
        for note in Notification.objects.filter(recipient=self.student):
            self.assertIsNotNone(note.time_read)

    def test_mark_all_unread__single_update_sets_unread_and_clears_time_read(self):
        """mark_all_unread marks read notifications unread and clears time_read in
        one UPDATE (the previous two-update version left time_read set)."""
        baker.make(
            Notification, recipient=self.student, unread=False, time_read=timezone.now(), _quantity=3,
        )
        self.assertEqual(Notification.objects.all_read(self.student).count(), 3)

        with CaptureQueriesContext(connection) as ctx:
            Notification.objects.all().mark_all_unread(self.student)

        updates = [q for q in ctx.captured_queries if q['sql'].lstrip().upper().startswith('UPDATE')]
        self.assertEqual(len(updates), 1)

        self.assertEqual(Notification.objects.all_read(self.student).count(), 0)
        for note in Notification.objects.filter(recipient=self.student):
            self.assertTrue(note.unread)
            self.assertIsNone(note.time_read)

    def test_url_correct_comment_hash__appends_comment_anchor(self):
        """get_url() and str() append a #comment-<id> anchor only when the notification has a comment action."""
        # create notification with comment as an action and corresponding verb
        comment = baker.make('comments.Comment')
        new_notification(
            self.student,
            action=comment,
            target=baker.make('announcements.Announcement'),
            recipient=self.student,
            affected_users=[self.teacher],
            verb="commented on",
        )
        # since new_notification does not return anything, have to get it from query
        notification = Notification.objects.order_by('id').last()
        self.assertEqual(notification.verb, "commented on")
        self.assertEqual(notification.action_object_id, comment.id)

        # Base case: check if notification without comment does not have hash
        base_notification = Notification.objects.create(
            recipient=self.student,
            sender_content_type=ContentType.objects.get_for_model(self.teacher),
            sender_object_id=self.teacher.id,
            verb="sent you a notification"
        )
        base_notification.full_clean()
        base_notification.save()

        self.assertNotIn('#comment-', base_notification.get_url())
        self.assertNotIn('#comment-', str(base_notification))

        # check if notification with comment has a hash
        comment_hash = f'#comment-{comment.id}'
        self.assertIn(comment_hash, notification.get_url())
        self.assertIn(comment_hash, str(notification))

    def test_get_sender_display__support_admin_renders_as_bytedeck(self):
        """A notification sent by the deck's ByteDeck support account displays its
        actor as "Bytedeck" (the raw `admin` username would read like any other
        user), in both the notification-page rendering and the string form."""
        from django.conf import settings

        support_admin, _ = User.objects.get_or_create(username=settings.TENANT_DEFAULT_ADMIN_USERNAME)
        new_notification(support_admin, recipient=self.student, verb='sent a deck suspended warning.')

        notification = self.student.notifications.get()
        self.assertEqual(notification.get_sender_display(), 'Bytedeck')
        self.assertIn('Bytedeck sent a deck suspended warning.', notification.get_link())
        self.assertIn('Bytedeck sent a deck suspended warning.', str(notification))

    def test_get_sender_display__other_senders_keep_their_normal_form(self):
        """Any other sender renders exactly as before: its own string form (for a
        user, the username)."""
        new_notification(self.teacher, recipient=self.student, verb='tested.')

        notification = self.student.notifications.get()
        self.assertEqual(str(notification.get_sender_display()), str(self.teacher))
        self.assertIn(f'{self.teacher} tested.', notification.get_link())


class NotificationModel_html_strip_Test(TestCase):
    """
        This test class is specialized on testing the html_strip() method of Notification model
    """

    def setUp(self):
        """No per-test setup is required for html_strip() tests."""
        pass

    def test_notification_html_strip__check_with_no_html(self):
        """
            Base case test to see if html_strip() wont strip normal text
        """
        test_case = "TEST CASE 1 NO STRIPPED TAGS"
        expected_case = "TEST CASE 1 NO STRIPPED TAGS"

        self.assertEqual(
            Notification.html_strip(test_case),
            expected_case
        )

    def test_notification_html_strip__check_with_html(self):
        """
            Test that html_strip() strips out any html tags (excluding img).
            <img> tags are not tested here.
        """
        test_case = "<p>TEST CASE 2</p> WITH <h1>HTML</h1> TAGS"
        expected_case = "TEST CASE 2 WITH HTML TAGS"

        self.assertEqual(
            Notification.html_strip(test_case),
            expected_case
        )

    def test_notification_html_strip__check_with_img_tag(self):
        """
            Test that html_strip() wont strip out any img tags.
        """
        test_case = 'TEST CASE 3 WITH IMG <img src="SOURCE" style="should be empty"></img> TAG'
        expected_case = 'TEST CASE 3 WITH IMG <img height="20px" src="SOURCE" style="" width="auto"/> TAG'

        self.assertEqual(
            Notification.html_strip(test_case),
            expected_case
        )

    def test_notification_html_strip__check_with_html_and_img_tag(self):
        """
            Test that html_strip() strips out any html tags and excludes img tags.
        """
        test_case = '<h1>TEST CASE 4</h1> <p>HTML</p> AND IMG <img src="SOURCE" style="should be empty"></img> TAGS'
        expected_case = 'TEST CASE 4 HTML AND IMG <img height="20px" src="SOURCE" style="" width="auto"/> TAGS'

        self.assertEqual(
            Notification.html_strip(test_case),
            expected_case
        )

    def test_notification_html_strip__multiple_img_tags_are_not_mangled(self):
        """Content with more than one <img> keeps every image well-formed and resized.

        Regression for issue #1761: the previous index-based implementation spliced one
        image tag into the middle of another and dropped the resize, leaving oversized
        images and broken markup that wrecked the notification dropdown's layout.
        """
        test_case = (
            'A <img src="one.png" style="width: 50%;"> B <img src="two.png" style="width: 25%;"> C'
        )
        expected_case = (
            'A <img height="20px" src="one.png" style="" width="auto"/> '
            'B <img height="20px" src="two.png" style="" width="auto"/> C'
        )
        self.assertEqual(Notification.html_strip(test_case), expected_case)

    def test_notification_html_strip__truncates_long_text_with_ellipsis(self):
        """Text longer than the character limit is cut and gets a trailing ellipsis."""
        long_text = "x" * 200
        result = Notification.html_strip(long_text, char_limit=50)
        self.assertEqual(result, "x" * 50 + "...")

    def test_notification_html_strip__empty_and_none_return_empty_string(self):
        """Falsy input (empty string or None) yields an empty string, not an error."""
        self.assertEqual(Notification.html_strip(""), "")
        self.assertEqual(Notification.html_strip(None), "")

    def test_notification_html_strip__coerces_non_string_input(self):
        """A non-string value is coerced to str before stripping (e.g. an int)."""
        self.assertEqual(Notification.html_strip(12345), "12345")

    def test_notification_html_strip__strips_html_comments(self):
        """HTML comments are dropped, not rendered as visible text or counted toward the limit."""
        self.assertEqual(Notification.html_strip("a<!-- hidden -->b"), "ab")

    def test_notification_html_strip__resize_image_false_keeps_original_img(self):
        """With resize_image=False the <img> is preserved but not resized."""
        self.assertEqual(
            Notification.html_strip('<img src="SOURCE">', resize_image=False),
            '<img src="SOURCE"/>',
        )

    def test_notification_html_strip__truncation_drops_trailing_content(self):
        """Once the character limit is hit, later nodes (text and images) are dropped
        and the result is ellipsised."""
        test_case = 'ab <img src="x.png"> cd'
        # char_limit=1 is consumed by "a"; everything after is dropped.
        self.assertEqual(Notification.html_strip(test_case, char_limit=1), "a...")

class NotificationEscapingTest(ByteDeckTenantTestCase):
    """A notification's text is rendered with |safe, so it has to build itself safely.

    The values it interpolates are names people choose: a student's own preferred name
    reaches it through `Profile.__str__`, and a quest's name through the target object.
    """

    @classmethod
    def setUpTestData(cls):
        """Create a teacher and a student (a teacher must exist first or student creation fails)."""
        cls.teacher = Recipe(User, is_staff=True).make()
        cls.student = baker.make(User)

    def make_notification(self, **kwargs):
        """Build a notification sent by the teacher, for use as the subject of a test.

        Args:
            **kwargs: fields to set on the Notification, overriding or adding to the
                recipient and sender this sets up.

        Returns:
            Notification: the saved notification.
        """
        return baker.make(
            Notification,
            recipient=self.student,
            sender_content_type=ContentType.objects.get_for_model(self.teacher),
            sender_object_id=self.teacher.id,
            **kwargs,
        )

    def test_str__escapes_the_actors_name(self):
        """A student's own profile name is escaped, wherever they are named.

        `preferred_name` is student-editable and lands in `Profile.__str__`, which is what
        the staff "New user registered" notice names, so it reaches every teacher's
        notification list.
        """
        self.student.first_name = 'Sam'
        self.student.last_name = 'Jones'
        self.student.save()
        profile = self.student.profile
        profile.preferred_name = '<img src=x onerror="alert(1)">'
        profile.save()
        # as the target, which is how the "New user registered" notice names them,
        notification = self.make_notification(
            verb='registered', target_content_type=ContentType.objects.get_for_model(profile),
            target_object_id=profile.id,
        )

        rendered = str(notification)

        self.assertNotIn('<img src=x onerror="alert(1)">', rendered)
        self.assertIn('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;', rendered)

        # and as the sender, which is the other place a name is interpolated.
        as_sender = baker.make(
            Notification,
            recipient=self.teacher,
            sender_content_type=ContentType.objects.get_for_model(profile),
            sender_object_id=profile.id,
            verb='did something',
        )

        rendered = str(as_sender)

        self.assertNotIn('<img src=x onerror="alert(1)">', rendered)
        self.assertIn('&lt;img src=x onerror=&quot;alert(1)&quot;&gt;', rendered)

    def test_str__escapes_the_target_objects_name(self):
        """A quest named with markup is named as text, not rendered."""
        quest = baker.make('quest_manager.Quest', name='Quest <script>alert(1)</script>')
        notification = self.make_notification(
            verb='commented on', target_content_type=ContentType.objects.get_for_model(quest),
            target_object_id=quest.id,
        )

        rendered = str(notification)

        self.assertNotIn('<script>alert(1)</script>', rendered)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', rendered)

    def test_str__escapes_the_verb_and_the_link_text(self):
        """The verb and link text are plain fields, so they are escaped too."""
        notification = self.make_notification(
            verb='did <b>something</b>', target_url='/quests/', target_link_text='<b>here</b>',
        )

        rendered = str(notification)

        self.assertNotIn('<b>something</b>', rendered)
        self.assertNotIn('<b>here</b>', rendered)
        self.assertIn('&lt;b&gt;here&lt;/b&gt;', rendered)

    def test_str__keeps_the_image_preview_of_a_comment(self):
        """An image in the previewed comment survives, which is the point of html_strip.

        The action is the one value that stays live: `html_strip` keeps `<img>` on purpose
        so an image in a comment shows in the notification dropdown, and what it is given
        is comment HTML that was sanitized when it was saved.
        """
        comment = baker.make('comments.Comment', text='<img src="/media/pic.png">')
        quest = baker.make('quest_manager.Quest', name='A Quest')
        notification = self.make_notification(
            verb='commented on',
            target_content_type=ContentType.objects.get_for_model(quest), target_object_id=quest.id,
            action_content_type=ContentType.objects.get_for_model(comment), action_object_id=comment.id,
        )

        rendered = str(notification)

        self.assertIn('<img', rendered)
        self.assertNotIn('&lt;img', rendered)

    def test_str__sanitizes_an_action_that_is_not_a_comment(self):
        """The action keeps its image preview, but never an event handler.

        `action` is the one value rendered as markup, and it is not always comment HTML:
        the Library push sends the quest or campaign as the action, and a badge assertion
        arrives the same way, so what it holds is some model's `__str__` and whatever the
        person who named it typed.
        """
        quest = baker.make('quest_manager.Quest', name='<img src=x onerror="alert(1)">')
        target = baker.make('quest_manager.Quest', name='Target Quest')
        notification = self.make_notification(
            verb='shared',
            target_content_type=ContentType.objects.get_for_model(target), target_object_id=target.id,
            action_content_type=ContentType.objects.get_for_model(quest), action_object_id=quest.id,
        )

        rendered = str(notification)

        self.assertNotIn('onerror', rendered)
        self.assertIn('<img', rendered)

    def test_str__is_marked_safe_so_the_templates_can_render_it(self):
        """The result is a safe string: the templates render it with |safe."""
        notification = self.make_notification(verb='did something')

        self.assertTrue(hasattr(str(notification), '__html__'))
